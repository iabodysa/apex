"""Accommodation Material Transfer controller — moves Custody Article / Maintenance
Material stock between two building stores via the Accommodation Stock Ledger.

Lifecycle: Draft -> (submit) In Transit -> (mark_received) Received; cancel reverses.
On submit the ship leg leaves the source store (qty in transit, in neither store);
on receipt the receive leg lands in the destination store. Availability is checked
against the source store balance at submit time."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

VOUCHER_TYPE = "Accommodation Material Transfer"


class AccommodationMaterialTransfer(Document):
    pass


def validate(doc, method=None):
    if not doc.items:
        frappe.throw(_("At least one item is required on a Material Transfer."))
    if doc.from_building and doc.to_building and doc.from_building == doc.to_building:
        frappe.throw(_("Source and destination buildings must be different."))
    from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        _resolve_item,
    )
    for row in doc.items:
        if (row.qty or 0) <= 0:
            frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))
        if row.item_type and row.item:
            item_name, uom, _cost = _resolve_item(row.item_type, row.item)
            row.item_name = item_name
            row.uom = uom


def on_submit(doc, method=None):
    """Post the ship leg out of the source store and mark the transfer In Transit."""
    _assert_source_availability(doc)
    _post_ship_leg(doc)
    doc.db_set("status", "In Transit")


def _assert_source_availability(doc):
    """Reject the transfer if the source store cannot cover the requested quantity
    for any item (quantities aggregated per item, in case of duplicate rows)."""
    from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        get_store_balance,
    )
    needed = {}
    for row in doc.items:
        needed[(row.item_type, row.item)] = needed.get((row.item_type, row.item), 0) + flt(row.qty)
    for (item_type, item), qty in needed.items():
        available = get_store_balance(item_type, item, doc.from_building)
        if qty > available:
            frappe.throw(
                _("Cannot transfer {0} unit(s) of {1} from {2}: only {3} available in the store.").format(
                    qty, item, doc.from_building, available
                )
            )


def _post_ship_leg(doc):
    """Stock leaves the source store (employee unset). Idempotent."""
    from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        post_stock_entry, has_stock_entries,
    )
    if has_stock_entries(VOUCHER_TYPE, doc.name):
        return
    for row in doc.items:
        post_stock_entry(
            item_type=row.item_type, item=row.item, qty=-flt(row.qty),
            building=doc.from_building, employee=None,
            from_building=doc.from_building, to_building=doc.to_building,
            voucher_type=VOUCHER_TYPE, voucher_no=doc.name, voucher_detail_no=row.name,
            posting_date=doc.transfer_date,
        )


@frappe.whitelist()
def mark_received(transfer: str, received_date: str = None):
    """Post the receive leg into the destination store and mark the transfer
    Received. Only valid for a submitted, In-Transit transfer; idempotent on status."""
    doc = frappe.get_doc(VOUCHER_TYPE, transfer)
    if doc.docstatus != 1:
        frappe.throw(_("Only a submitted transfer can be received."))
    if doc.status == "Received":
        return doc.name
    if doc.status != "In Transit":
        frappe.throw(_("Transfer {0} is not In Transit.").format(doc.name))
    from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        post_stock_entry,
    )
    rcv_date = received_date or today()
    for row in doc.items:
        post_stock_entry(
            item_type=row.item_type, item=row.item, qty=flt(row.qty),
            building=doc.to_building, employee=None,
            from_building=doc.from_building, to_building=doc.to_building,
            voucher_type=VOUCHER_TYPE, voucher_no=doc.name, voucher_detail_no=row.name,
            posting_date=rcv_date,
        )
    doc.db_set("received_date", rcv_date)
    doc.db_set("status", "Received")
    _notify_finance_on_cost_center_shift(doc)
    return doc.name


def _notify_finance_on_cost_center_shift(doc):
    """Memo-only: if the source and destination buildings sit on different cost
    centers, the stock liability has shifted between them. We do NOT post any GL
    Entry — we only email Finance so they can record the cross-charge manually,
    and only when the admin has opted in via Habitat Settings."""
    if not frappe.db.get_single_value("Habitat Settings", "notify_finance_on_liability_transfer"):
        return
    from_cc = frappe.db.get_value("Accommodation Building", doc.from_building, "default_cost_center")
    to_cc = frappe.db.get_value("Accommodation Building", doc.to_building, "default_cost_center")
    if not from_cc or not to_cc or from_cc == to_cc:
        return

    recipients = []
    email = frappe.db.get_single_value("Habitat Settings", "finance_notification_email")
    if email:
        recipients = [email]
    else:
        recipients = _role_emails("Finance Manager")
    if not recipients:
        return

    subject = _("Cross-cost-center material transfer: {0}").format(doc.name)
    lines = "".join(
        "<li>{0} &times; {1} ({2})</li>".format(flt(r.qty), frappe.utils.escape_html(r.item_name or r.item), r.uom or "")
        for r in doc.items
    )
    message = _(
        "Material Transfer {0} moved stock from {1} (cost center {2}) to {3} (cost center {4}). "
        "This is a memo only — no GL Entry was posted. Please record the cross-charge if required."
    ).format(doc.name, doc.from_building, from_cc, doc.to_building, to_cc) + "<ul>{0}</ul>".format(lines)

    try:
        frappe.sendmail(recipients=recipients, subject=subject, message=message, reference_doctype=VOUCHER_TYPE, reference_name=doc.name)
    except Exception:
        frappe.log_error(title="Material Transfer finance memo failed", message=frappe.get_traceback())


def _role_emails(role):
    users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
    if not users:
        return []
    return frappe.get_all(
        "User", filters={"name": ["in", users], "enabled": 1, "email": ["is", "set"]}, pluck="email"
    )


def on_cancel(doc, method=None):
    """Reverse every ledger row this transfer posted (ship and, if any, receive legs)."""
    from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        reverse_stock_entries,
    )
    reverse_stock_entries(VOUCHER_TYPE, doc.name)
    doc.db_set("status", "Cancelled")
