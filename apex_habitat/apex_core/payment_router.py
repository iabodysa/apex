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

from apex_habitat.apex_core.doctype.apex_settings.apex_settings import gl_posting_enabled

SOURCE_DOCTYPE = "Salis Payment Request"

# [#asggke]
DEFAULT_TARGET_DOCTYPE = "Payment Request"


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
    finance-approved Salis Payment Request, then stamp ``linked_payment_entry``.
    Idempotent: returns the existing payment when already linked. Submit is gated on
    ``auto_submit_target`` + a submittable target + ``enable_gl_posting`` (submit is
    what posts the native doc's GL). The create uses ``ignore_permissions``, so the
    caller's write/submit permission on the request is enforced just below. [T-151]
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

    target = frappe.new_doc(target_doctype)
    _apply_field_map(target, source, settings.field_map or [])
    # [#5dt0v6]
    _ensure_target_currency(target, source)
    target.insert(ignore_permissions=True)

    # [#92jq1c]
    if settings.auto_submit_target and target.meta.is_submittable and gl_posting_enabled():
        target.submit()

    # [#rx80aq]
    source.db_set("linked_payment_entry", target.name)

    return target.name


@frappe.whitelist(methods=["POST"])
def create_routed_payment(payment_request: str) -> str:
    """Whitelisted POST entry for the Create Payment desk action - a thin wrapper
    over :func:`route_payment` (which enforces the caller's permission). POST-only so
    a cacheable GET cannot trigger this write (guarded in test_http_enforcement).
    """
    return route_payment(payment_request)
