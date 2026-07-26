# Copyright (c) 2026, AFMCO Support Services Co. Ltd and contributors
# [#j03s5a]
"""Accommodation Stock Ledger — read-only, system-written quantity ledger for the
decentralized internal-store engine. Each Accommodation Building is its own store.
Rows are posted only through the helpers below (never created manually); a blank
employee means the stock sits unassigned in the building's store, a set employee
means it is in that employee's custody. Reversals are negative mirror entries."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class AccommodationStockLedger(Document):
    pass


def on_doctype_update():
    """Composite index (is_cancelled, item_type, employee) serving the custody /
    stock-balance access path (active rows of an item type for an employee). Added
    here — not only via a patch — so fresh installs, which mark patches complete
    without running them, also get it. Runs on app sync + every migrate; idempotent."""
    # [#asl9cx]
    from apex.apex_core.utils.ledger_index import add_index_guarded

    add_index_guarded(
        "Accommodation Stock Ledger",
        ["is_cancelled", "item_type", "employee"],
        "idx_asl_cancel_type_emp",
    )


# [#swxhdr]
_MASTER_FIELDS = {
    "Custody Article": ("article_name", "unit_of_measure", "standard_unit_cost"),
    "Maintenance Material": ("material_name", "default_uom", "estimated_unit_cost"),
}


def _resolve_item(item_type: str, item: str):
    fields = _MASTER_FIELDS.get(item_type)
    if not fields:
        return (item, "", 0.0)
    vals = frappe.db.get_value(item_type, item, list(fields), as_dict=True) or {}
    return (vals.get(fields[0]) or item, vals.get(fields[1]) or "", flt(vals.get(fields[2])))


def post_stock_entry(*, item_type, item, qty, building, voucher_type, voucher_no,
                     voucher_detail_no=None, employee=None, posting_date=None,
                     from_building=None, to_building=None, remarks=None, reversal_of=None):
    """Insert one signed-quantity Stock Ledger row. Denormalises item name/uom/cost,
    company and cost center from the source masters/building."""
    item_name, uom, unit_cost = _resolve_item(item_type, item)
    company, cost_center = frappe.db.get_value(
        "Building", building, ["company", "default_cost_center"]
    ) or (None, None)
    doc = frappe.get_doc({
        "doctype": "Accommodation Stock Ledger",
        "posting_date": posting_date or today(),
        "company": company,
        "item_type": item_type,
        "item": item,
        "item_name": item_name,
        "uom": uom,
        "signed_qty": flt(qty),
        "unit_cost": unit_cost,
        "building": building,
        "cost_center": cost_center,
        "employee": employee,
        "from_building": from_building,
        "to_building": to_building,
        "voucher_type": voucher_type,
        "voucher_no": voucher_no,
        "voucher_detail_no": voucher_detail_no,
        "reversal_of": reversal_of,
        "remarks": remarks,
    })
    doc.insert(ignore_permissions=True)  # audit-ok
    return doc.name


def get_store_balance(item_type: str, item: str, building: str, employee=None,
                      for_update: bool = False) -> float:
    """Live signed-quantity balance for one item in a building's store (employee
    unset) or in an employee's custody (employee set). Sums non-cancelled rows.

    for_update: take a SELECT ... FOR UPDATE on the summed rows so the balance read
    is a locking current-read. A draining caller passes for_update=True to close the
    TOCTOU race where two concurrent transfers/handovers both read the same balance,
    both pass the availability check, and both post ship legs that drive the store
    negative. The locking read serializes the second drain behind the first commit;
    InnoDB predicate locking also blocks it from racing in a new mirror row."""
    Ledger = frappe.qb.DocType("Accommodation Stock Ledger")
    q = (
        frappe.qb.from_(Ledger)
        .select(Ledger.signed_qty)
        .where(Ledger.item_type == item_type)
        .where(Ledger.item == item)
        .where(Ledger.building == building)
        .where(Ledger.is_cancelled == 0)
    )
    q = q.where(Ledger.employee == employee) if employee else q.where(Ledger.employee.isnull())
    if for_update:
        q = q.for_update()
    rows = q.run(as_dict=True)
    return flt(sum(flt(r.signed_qty) for r in rows))


def has_stock_entries(voucher_type: str, voucher_no: str) -> bool:
    """Idempotency guard: True if this voucher already has live (non-cancelled) rows."""
    return bool(frappe.db.exists(
        "Accommodation Stock Ledger",
        {"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
    ))


def reverse_stock_entries(voucher_type: str, voucher_no: str) -> None:
    """Reverse (do not delete) all live rows of a voucher: post negative mirror
    entries and mark the originals cancelled. Idempotent."""
    rows = frappe.get_all(
        "Accommodation Stock Ledger",
        filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
        fields=["name", "item_type", "item", "signed_qty", "building", "employee",
                "from_building", "to_building"],
    )
    for r in rows:
        rev = post_stock_entry(
            item_type=r.item_type, item=r.item, qty=-flt(r.signed_qty), building=r.building,
            employee=r.employee, voucher_type=voucher_type, voucher_no=voucher_no,
            from_building=r.from_building, to_building=r.to_building,
            reversal_of=r.name, remarks="Reversal",
        )
        # [#4eui8g]
        frappe.db.set_value("Accommodation Stock Ledger", r.name, "is_cancelled", 1)
        frappe.db.set_value("Accommodation Stock Ledger", rev, "is_cancelled", 1)


def reverse_and_mark_cancelled(doc, voucher_type: str) -> None:
    """The whole on_cancel routine every stock voucher shares: reverse each ledger
    row this voucher posted, then stamp the voucher Cancelled. Reversal is keyed on
    voucher_type/voucher_no only, so it never reads the doc and the two steps are
    order-independent."""
    reverse_stock_entries(voucher_type, doc.name)
    doc.db_set("status", "Cancelled")
