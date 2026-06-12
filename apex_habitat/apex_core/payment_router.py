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

Boundary: this layer only **routes** the payment record. General Ledger posting
is governed separately by ``enable_gl_posting`` (Apex Settings); the router
writes no GL / Journal Entry here.
"""

from __future__ import annotations

import frappe
from frappe import _

SOURCE_DOCTYPE = "Salis Payment Request"

# A Salis Payment Request is finance-approved once it enters one of these
# states. Mirrors ``salis_payment_request._FINANCE_GATED_STATUSES`` - entry into
# either is the Finance-exclusive, SoD-guarded gate.
_APPROVED_STATUSES = {"Approved by Finance", "Paid"}


def _is_finance_approved(source) -> bool:
    """True when the request has cleared the Finance approval gate.

    Approved is proven by the stamped approver (``finance_approved_by``, set by
    the controller's defence-in-depth gate) OR by an approved/paid status. Either
    is sufficient; both are set together on the normal workflow path.
    """
    return bool(source.get("finance_approved_by")) or source.get("status") in _APPROVED_STATUSES


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
            # Defensive: validate() blocks this, but never write a blank key.
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
      1. Read Payment Routing Settings; require a target DocType (else throw).
      2. Load the source request; require it to be finance-approved (else throw).
      3. Idempotency: if it already carries ``linked_payment_entry``, return that
         (never create a second payment).
      4. Build the target via the field map, insert it, and - when
         ``auto_submit_target`` and the target is submittable - submit it.
      5. Stamp ``linked_payment_entry`` on the request with the created name.

    This is an authorized finance action invoked behind the workflow/permission
    gates, so the create is performed with ``ignore_permissions=True`` (the
    target payment DocType's own roles may differ from the request's). Returns
    the created (or already-linked) payment document name.
    """
    settings = frappe.get_single("Payment Routing Settings")
    target_doctype = settings.target_payment_doctype
    if not target_doctype:
        frappe.throw(
            _("Configure the target payment DocType in Payment Routing Settings first.")
        )

    source = frappe.get_doc(SOURCE_DOCTYPE, payment_request)

    if not _is_finance_approved(source):
        frappe.throw(
            _("This payment request is not finance-approved yet; it cannot be paid.")
        )

    # Idempotency - a request routes to exactly one payment document.
    if source.linked_payment_entry:
        return source.linked_payment_entry

    target = frappe.new_doc(target_doctype)
    _apply_field_map(target, source, settings.field_map or [])
    target.insert(ignore_permissions=True)

    if settings.auto_submit_target and target.meta.is_submittable:
        target.submit()

    # Stamp the link back onto the request. db_set persists immediately without a
    # full save, so it does not re-run the request's validate/finance gate.
    source.db_set("linked_payment_entry", target.name)

    return target.name


@frappe.whitelist(methods=["POST"])
def create_routed_payment(payment_request: str) -> str:
    """Whitelisted POST entry point for the Create Payment desk action.

    POST-only: this performs a write (creates the payment, stamps the link), so a
    cacheable GET must never trigger it (CSRF / cache-poisoning guard enforced by
    ``tests/test_http_enforcement.py``). Delegates to :func:`route_payment`.
    """
    return route_payment(payment_request)
