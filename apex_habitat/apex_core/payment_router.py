"""Payment Router - configurable, mapping-driven payment integration.

The payment target differs per company / per server: one deployment posts an
ERPNext Payment Entry, another a Payment Order, another a client's own custom
payment DocType. Hard-wiring the target is wrong - it is a setting. This module
reads **Payment Routing Settings** (a Single config record with a child-table
field map) and builds the target payment document from a finance-approved
**Salis Payment Request** by applying that mapping - with **no hard-coded
per-DocType branches**.

Why a custom construct and not ``frappe.model.mapper.get_mapped_doc``: that
helper's ``field_map`` is supplied in Python at call time, so the source ->
target fieldnames are baked into code. The requirement is **config-time**
mapping a deployment admin edits without code. The dispatch here is still thin:
it uses native ``frappe.new_doc`` / ``insert`` / ``submit`` and the target's own
meta ``is_submittable``; only the mapping schema is custom.

Boundary: this layer only **routes** the payment record - it writes no GL /
Journal Entry of its own. General Ledger posting is governed separately by
``enable_gl_posting`` (Apex Settings). In Frappe a payment document posts its
ledger effect from its **own** ``on_submit`` (e.g. ERPNext ``Payment Request``
-> Payment Entry -> GL); so when GL posting is OFF the router must not *submit*
a GL-posting target. The flag therefore gates the auto-submit step: OFF (the
factory default) leaves the routed payment in Draft and nothing touches the
ledger; ON lets ``auto_submit_target`` submit it so the native doc posts.

Default target: when ``target_payment_doctype`` is unconfigured the router falls
back to Frappe's native, submittable **Payment Request** DocType - the framework
primitive for a payment intent - rather than throwing or inventing a custom doc.
A deployment overrides it by setting the target (and, if a client ships its own
payment DocType, by selecting that instead).
"""

from __future__ import annotations

import frappe
from frappe import _

from apex_habitat.apex_core.doctype.apex_settings.apex_settings import gl_posting_enabled

SOURCE_DOCTYPE = "Salis Payment Request"

# [#fp9fyu]
# [#t9qszv]
# [#cufhur]
# [#642vqq]
DEFAULT_TARGET_DOCTYPE = "Payment Request"


def get_target_doctype(settings=None) -> str:
    """Resolve the payment DocType to build, defaulting to native Payment Request.

    ``Payment Routing Settings.target_payment_doctype`` wins when set; otherwise
    the native ``Payment Request`` primitive is used so the flow works out of the
    box with no configuration.
    """
    settings = settings or frappe.get_single("Payment Routing Settings")
    return settings.target_payment_doctype or DEFAULT_TARGET_DOCTYPE

# [#rcwf7j]
# [#dyphhj]
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
            # [#6v9bve]
            continue
        if row.is_static:
            value = row.static_value
        else:
            source_field = (row.source_fieldname or "").strip()
            value = source.get(source_field) if source_field else None
        target.set(target_field, value)


def route_payment(payment_request: str) -> str:
    """Create the configured target payment document from a Salis Payment Request.

    Steps:
      1. Read Payment Routing Settings; resolve the target DocType, defaulting to
         native ``Payment Request`` when none is configured (never throws for an
         unconfigured target - the native primitive is the default).
      2. Load the source request; require it to be finance-approved (else throw).
      3. Idempotency: if it already carries ``linked_payment_entry``, return that
         (never create a second payment).
      4. Build the target via the field map, insert it, and - when
         ``auto_submit_target``, the target is submittable, AND GL posting is
         enabled - submit it. Submitting is what drives the native doc's own GL
         posting, so it is gated on ``enable_gl_posting``; with the flag OFF the
         payment is routed but left in Draft and nothing posts to the ledger.
      5. Stamp ``linked_payment_entry`` on the request with the created name.

    This is an authorized finance action invoked behind the workflow/permission
    gates, so the create is performed with ``ignore_permissions=True`` (the
    target payment DocType's own roles may differ from the request's). Returns
    the created (or already-linked) payment document name.
    """
    settings = frappe.get_single("Payment Routing Settings")
    target_doctype = get_target_doctype(settings)

    # [#58agmm]
    # [#62d4rs]
    # [#1ymyoq]
    # [#93rjxu]
    frappe.db.get_value(SOURCE_DOCTYPE, payment_request, "name", for_update=True)
    source = frappe.get_doc(SOURCE_DOCTYPE, payment_request)

    # [#dpzek9]
    # [#th1tyi]
    # [#kek961]
    # [#p7p83c]
    # [#an7p80]
    frappe.has_permission(SOURCE_DOCTYPE, "write", doc=source, throw=True)
    frappe.has_permission(SOURCE_DOCTYPE, "submit", doc=source, throw=True)

    if not _is_finance_approved(source):
        frappe.throw(
            _("This payment request is not finance-approved yet; it cannot be paid.")
        )

    # [#tksu31]
    if source.linked_payment_entry:
        return source.linked_payment_entry

    target = frappe.new_doc(target_doctype)
    _apply_field_map(target, source, settings.field_map or [])
    # [#4gxinh]
    # [#tjvbch]
    # [#2yxt5g]
    _ensure_target_currency(target, source)
    target.insert(ignore_permissions=True)

    # [#ljvbql]
    # [#450dmg]
    # [#oy2d3o]
    # [#2xccvh]
    if settings.auto_submit_target and target.meta.is_submittable and gl_posting_enabled():
        target.submit()

    # [#4fpafg]
    # [#p48huq]
    source.db_set("linked_payment_entry", target.name)

    return target.name


@frappe.whitelist(methods=["POST"])
def create_routed_payment(payment_request: str) -> str:
    """Whitelisted POST entry for the Create Payment desk action.

    POST-only so a cacheable GET can never trigger this write (CSRF/cache guard in
    ``tests/test_http_enforcement.py``). The caller's permission on the source
    request is enforced at the chokepoint :func:`route_payment` (co-located with the
    ``ignore_permissions`` side effects), so every caller is gated. Thin wrapper.
    """
    return route_payment(payment_request)
