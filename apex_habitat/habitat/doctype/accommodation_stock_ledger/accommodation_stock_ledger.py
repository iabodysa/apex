# Copyright (c) 2026, Abdullah Fahad Al-Mutairi Co. (AFMCO) and contributors
# For license information, please see license.txt
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


# item_type -> (name_field, uom_field, unit_cost_field) on the master doctype
_MASTER_FIELDS = {
    "Custody Article": ("article_name", "unit_of_measure", "standard_unit_cost_sar"),
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
        "Accommodation Building", building, ["company", "default_cost_center"]
    ) or (None, None)
    doc = frappe.get_doc({
        "doctype": "Accommodation Stock Ledger",
        "posting_date": posting_date or today(),
        "company": company,
        "item_type": item_type,
        "item": item,
        "item_name": item_name,
        "uom": uom,
        "qty": flt(qty),
        "unit_cost_sar": unit_cost,
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
        fields=["name", "item_type", "item", "qty", "building", "employee",
                "from_building", "to_building"],
    )
    for r in rows:
        rev = post_stock_entry(
            item_type=r.item_type, item=r.item, qty=-flt(r.qty), building=r.building,
            employee=r.employee, voucher_type=voucher_type, voucher_no=voucher_no,
            from_building=r.from_building, to_building=r.to_building,
            reversal_of=r.name, remarks="Reversal",
        )
        # Mark BOTH the original and its reversal cancelled so they net to zero in
        # balance queries (which sum where is_cancelled = 0) while keeping the audit pair.
        frappe.db.set_value("Accommodation Stock Ledger", r.name, "is_cancelled", 1)
        frappe.db.set_value("Accommodation Stock Ledger", rev, "is_cancelled", 1)
