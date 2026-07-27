# Copyright (c) 2026, AFMCO and contributors
"""Payment Router - build the configured target payment from a finance-approved
Salis Payment Request via the Payment Routing Settings field map (config-time, no
hard-coded per-DocType branches); defaults to the native Payment Request when the
target is unconfigured.

Boundary: this layer routes only - it posts no GL itself. ``enable_gl_posting``
(Apex Settings) gates the auto-submit step, because a native payment posts its
ledger from its own ``on_submit``; OFF leaves the routed doc in Draft. [T-151] the
fuller rationale (config-time mapping vs get_mapped_doc, the GL mechanics) is in the
commit that tightened this docstring.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model import default_fields

from apex.apex_core.doctype.apex_settings.apex_settings import gl_posting_enabled

SOURCE_DOCTYPE = "Salis Payment Request"

# [#asggke]
DEFAULT_TARGET_DOCTYPE = "Payment Request"

# The link-type companion the router stamps beside the payment name, so the
# Dynamic Link on the source can never name a DocType other than the one built.
LINK_DOCTYPE_FIELD = "linked_payment_doctype"
LINK_NAME_FIELD = "linked_payment_entry"


def get_target_doctype(settings=None) -> str:
    """Resolve the payment DocType to build, defaulting to native Payment Request.

    ``Payment Routing Settings.target_payment_doctype`` wins when set; otherwise
    the native ``Payment Request`` primitive is used so the flow works out of the
    box with no configuration.
    """
    settings = settings or frappe.get_single("Payment Routing Settings")
    return settings.target_payment_doctype or DEFAULT_TARGET_DOCTYPE


@frappe.whitelist()
def get_target_payment_doctype() -> str:
    """Whitelisted read of the configured target payment DocType.

    The Accommodation Lease ``Generate Payment`` button reads this to decide which
    payment document to build, replacing the retired
    ``Apex Settings.default_payment_method`` Select. Read-only and unparameterised,
    so any desk user may call it. Returns the native ``Payment Request`` default
    when the router is unconfigured.
    """
    return get_target_doctype()


def require_configured_target(built_doctype: str) -> None:
    """Refuse when the deployment's configured payment target is not what the caller builds.

    For a surface that can route ANY target, :func:`route_payment` is the answer: it
    reads the configured target and the field map and builds whatever they name. A
    surface that can only ever produce ONE document type cannot do that, because the
    field map is written against :data:`SOURCE_DOCTYPE` fields and describes no other
    source. Its only honest options are to obey the configuration or to refuse.

    So it refuses. Quietly building a different document type than the one configured
    is the failure this exists to stop: the operator sees a plausible payment and never
    learns the deployment's routing choice was ignored on this one screen.
    """
    configured = get_target_doctype()
    if configured == built_doctype:
        return
    frappe.throw(
        _(
            "This site is configured to raise payments as {0}, but this action can only create a {1} allocated against the supplier's invoice. Raise this payment from a {2}, which builds the configured target, or set Target Payment DocType to {1} in Payment Routing Settings."
        ).format(_(configured), _(built_doctype), _(SOURCE_DOCTYPE)),
        title=_("Payment Target Mismatch"),
    )


def validate_target_doctype(target_doctype) -> None:
    """Refuse a structurally impossible payment target BEFORE anything is built.

    ``frappe.new_doc(dt).insert()`` succeeds for far more than payment documents,
    so without this the router turns a config typo into a convincing artefact that
    is not a payment - worse than refusing, because nobody re-reads it. Three
    refusals, each a real failure mode:

    * missing - the operator named a DocType this site does not have (an optional
      client app that was never installed). Silently falling back to the native
      default would pay every request through the wrong document.
    * Single - ``insert`` on a Single writes ``tabSingles``, so routing a payment
      would OVERWRITE that settings record rather than create anything.
    * child table - the row would be inserted parentless and belong to nothing.

    Deliberately structural, not semantic: the router supports any client payment
    DocType by design, so it refuses what cannot be a document at all rather than
    policing a whitelist it has no authority to define.
    """
    target_doctype = (target_doctype or "").strip()
    if not target_doctype:
        frappe.throw(
            _("No payment target is set and no default could be resolved, so no payment can be created."),
            title=_("Invalid Payment Target"),
        )
    if not frappe.db.exists("DocType", target_doctype):
        frappe.throw(
            _(
                "Payment target {0} is not installed on this site. Choose a payment DocType that exists here, or clear the Target Payment DocType to use the native {1}."
            ).format(target_doctype, DEFAULT_TARGET_DOCTYPE),
            title=_("Invalid Payment Target"),
        )
    meta = frappe.get_meta(target_doctype)
    if meta.issingle:
        frappe.throw(
            _(
                "Payment target {0} is a Single settings record, so creating a payment would overwrite it instead of adding one. Choose a normal payment DocType."
            ).format(target_doctype),
            title=_("Invalid Payment Target"),
        )
    if meta.istable:
        frappe.throw(
            _(
                "Payment target {0} is a child table row, which cannot exist on its own. Choose the parent payment DocType instead."
            ).format(target_doctype),
            title=_("Invalid Payment Target"),
        )


def validate_field_map(target_doctype, field_map) -> None:
    """Refuse a field map that cannot build the target, BEFORE any insert.

    Shape checks (a row names a target, names it once, and carries either a source
    field or a static value) plus the check that actually stops a wrong payment:
    both fieldnames must EXIST. ``BaseDocument.set`` writes to ``__dict__`` with no
    meta check and ``get_valid_dict`` then keeps only ``meta.get_valid_columns()``,
    so a mistyped target fieldname is dropped in silence and the payment is created
    with that field simply unset - a 0.00 payment that looks entirely normal. A
    mistyped SOURCE fieldname is worse still: ``source.get`` returns ``None``, so
    the field is written, just blank.

    Called from the controller (config time) AND from the router (run time),
    because ``db_set`` / raw SQL / a patch can all write the Single while skipping
    ``validate`` - a control that lived only in the controller would be bypassed.
    """
    target_meta = frappe.get_meta(target_doctype)
    # get_valid_columns() is exactly the set that survives an insert.
    writable = set(target_meta.get_valid_columns())
    source_meta = frappe.get_meta(SOURCE_DOCTYPE)
    seen = set()
    for row in field_map or []:
        target_field = (row.target_fieldname or "").strip()
        if not target_field:
            frappe.throw(
                _("Field Map row {0}: Target Fieldname is required.").format(row.idx)
            )
        if target_field in seen:
            frappe.throw(
                _("Field Map row {0}: Target Fieldname {1} is mapped more than once.").format(
                    row.idx, target_field
                )
            )
        seen.add(target_field)
        if target_field not in writable:
            frappe.throw(
                _(
                    "Field Map row {0}: {1} is not a field on the target payment DocType {2}, so it would be dropped and the payment created without it. Fix the fieldname."
                ).format(row.idx, target_field, target_doctype),
                title=_("Invalid Payment Field Map"),
            )
        if row.is_static:
            # [#hju7o1]
            if (row.source_fieldname or "").strip():
                frappe.throw(
                    _("Field Map row {0}: clear Source Fieldname on a Static row.").format(
                        row.idx
                    )
                )
            continue
        source_field = (row.source_fieldname or "").strip()
        if not source_field:
            frappe.throw(
                _("Field Map row {0}: Source Fieldname is required when the row is not Static.").format(
                    row.idx
                )
            )
        if not (source_meta.has_field(source_field) or source_field in default_fields):
            frappe.throw(
                _(
                    "Field Map row {0}: {1} is not a field on {2}, so the target field would be written blank. Fix the fieldname."
                ).format(row.idx, source_field, SOURCE_DOCTYPE),
                title=_("Invalid Payment Field Map"),
            )


# [#qj7x3p]
_FALLBACK_CURRENCY = "SAR"


def _default_currency(source) -> str:
    """Resolve the transaction currency for the routed target.

    A real payment document (e.g. the native Payment Request) is currency-bearing,
    but a Salis Payment Request has no ``currency`` field. Default it to the
    source company's default currency when a company is set, else to the
    single-currency baseline (``SAR``). Never throws - currency resolution must
    not block a finance-approved route.
    """
    company = source.get("company")
    if company:
        currency = frappe.get_cached_value("Company", company, "default_currency")
        if currency:
            return currency
    return _FALLBACK_CURRENCY


def _ensure_target_currency(target, source) -> None:
    """Stamp a transaction ``currency`` on the target if it has the field unset.

    The config-time field map may not include ``currency`` (the default-build
    case), yet a native payment doc needs one. When the target DocType actually
    has a ``currency`` field and the map left it blank, default it from the
    source's company (or the ``SAR`` baseline) so the native default integration
    produces a valid, currency-bearing payment. Targets without a ``currency``
    field (e.g. Note, the stub) are untouched - no per-DocType branch.
    """
    if not target.meta.has_field("currency"):
        return
    if target.get("currency"):
        return
    target.currency = _default_currency(source)


def _is_finance_approved(source) -> bool:
    """True when the request has cleared the Finance approval gate.

    Approval is proven SOLELY by the stamped approver ``finance_approved_by``,
    which the source controller's finance gate sets on entry to any
    finance-gated state, after enforcing the finance-role and Segregation-of-
    Duties checks. The mutable ``status`` field is deliberately NOT trusted: a
    write that bypasses the controller's ``validate`` (e.g. a direct ``db_set``
    or status edit) could land "Paid"/"Approved by Finance" without ever
    clearing the gate, so routing a real payment off the status alone would be a
    finance bypass. Gating on the immutable stamp is fail-closed - an un-stamped
    request never routes.
    """
    return bool(source.get("finance_approved_by"))


def _apply_field_map(target, source, field_map) -> None:
    """Populate ``target`` from ``source`` using the configured rows.

    Each row::

        target[target_fieldname] = static_value if is_static else source.get(source_fieldname)

    A static row writes the constant; a mapped row copies the named source field.
    No per-DocType logic - the rows are the only contract.
    """
    for row in field_map:
        target_field = (row.target_fieldname or "").strip()
        if not target_field:
            # [#ked8f9]
            continue
        if row.is_static:
            value = row.static_value
        else:
            source_field = (row.source_fieldname or "").strip()
            value = source.get(source_field) if source_field else None
        target.set(target_field, value)


def route_payment(payment_request: str) -> str:
    """Build (and optionally submit) the configured target payment from a
    finance-approved Salis Payment Request, then stamp the typed link back.
    Idempotent: returns the existing payment when already linked. Submit is gated on
    ``auto_submit_target`` + a submittable target + ``enable_gl_posting`` (submit is
    what posts the native doc's GL). The create uses ``ignore_permissions``, so the
    caller's write/submit permission on the request is enforced just below. [T-151]

    Fail-closed: the target and the field map are re-validated here, immediately
    before the build, and the link stamp carries the created document's own doctype.
    Refusing is the desired outcome for a bad config - a payment that merely LOOKS
    right is worse, because it is never read a second time.
    """
    settings = frappe.get_single("Payment Routing Settings")
    target_doctype = get_target_doctype(settings)

    # [#huthxu]
    frappe.db.get_value(SOURCE_DOCTYPE, payment_request, "name", for_update=True)
    source = frappe.get_doc(SOURCE_DOCTYPE, payment_request)

    # [#t1cwmn]
    frappe.has_permission(SOURCE_DOCTYPE, "write", doc=source, throw=True)
    frappe.has_permission(SOURCE_DOCTYPE, "submit", doc=source, throw=True)

    if not _is_finance_approved(source):
        frappe.throw(
            _("This payment request is not finance-approved yet; it cannot be paid.")
        )

    # [#qrnwir]
    if source.linked_payment_entry:
        return source.linked_payment_entry

    # Fail closed at the build boundary, not only in the Single's validate: db_set,
    # raw SQL and patches all write that config while skipping the controller.
    validate_target_doctype(target_doctype)
    validate_field_map(target_doctype, settings.field_map or [])

    target = frappe.new_doc(target_doctype)
    _apply_field_map(target, source, settings.field_map or [])
    # [#5dt0v6]
    _ensure_target_currency(target, source)
    target.insert(ignore_permissions=True)

    # [#92jq1c]
    if settings.auto_submit_target and target.meta.is_submittable and gl_posting_enabled():
        target.submit()

    # [#rx80aq] Both halves of the Dynamic Link are stamped from the document that
    # was actually created, so the stored type can never disagree with the value.
    source.db_set(
        {LINK_DOCTYPE_FIELD: target.doctype, LINK_NAME_FIELD: target.name}
    )

    return target.name


@frappe.whitelist(methods=["POST"])
def create_routed_payment(payment_request: str) -> str:
    """Whitelisted POST entry for the Create Payment desk action - a thin wrapper
    over :func:`route_payment` (which enforces the caller's permission). POST-only so
    a cacheable GET cannot trigger this write (guarded in test_http_enforcement).
    """
    return route_payment(payment_request)
