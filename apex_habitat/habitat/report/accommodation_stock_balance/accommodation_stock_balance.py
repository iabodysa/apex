# Copyright (c) 2026, AFMCO and contributors
"""Accommodation Stock Balance — current on-hand quantity per building store and
per employee custody, derived from the read-only Accommodation Stock Ledger.
Balance = sum(qty) of non-cancelled rows up to the as-on date, grouped by
building, item and holder (store vs. employee). Value = balance * unit cost."""

import frappe
from frappe import _
from frappe.utils import flt, today


def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 180},
        {"label": _("Holder"), "fieldname": "holder", "fieldtype": "Data", "width": 120},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 160},
        {"label": _("Item Type"), "fieldname": "item_type", "fieldtype": "Data", "width": 140},
        {"label": _("Item"), "fieldname": "item", "fieldtype": "Dynamic Link", "options": "item_type", "width": 140},
        {"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
        {"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 80},
        {"label": _("Balance Qty"), "fieldname": "balance_qty", "fieldtype": "Float", "width": 110},
        {"label": _("Unit Cost (SAR)"), "fieldname": "unit_cost_sar", "fieldtype": "Currency", "width": 130},
        {"label": _("Value (SAR)"), "fieldname": "value_sar", "fieldtype": "Currency", "width": 130},
    ]


def get_data(filters):
    conditions = {"is_cancelled": 0, "posting_date": ["<=", filters.get("as_on_date") or today()]}
    if filters.get("building"):
        conditions["building"] = filters["building"]
    if filters.get("item_type"):
        conditions["item_type"] = filters["item_type"]
    if filters.get("employee"):
        conditions["employee"] = filters["employee"]

    rows = frappe.get_all(
        "Accommodation Stock Ledger",
        filters=conditions,
        fields=["building", "employee", "item_type", "item", "item_name", "uom",
                "qty", "unit_cost_sar"],
    )

    # Aggregate signed qty per (building, holder, item).
    agg = {}
    for r in rows:
        key = (r.building, r.employee or "", r.item_type, r.item)
        bucket = agg.setdefault(key, {
            "building": r.building, "employee": r.employee, "item_type": r.item_type,
            "item": r.item, "item_name": r.item_name, "uom": r.uom,
            "unit_cost_sar": flt(r.unit_cost_sar), "balance_qty": 0.0,
        })
        bucket["balance_qty"] += flt(r.qty)
        if r.unit_cost_sar:
            bucket["unit_cost_sar"] = flt(r.unit_cost_sar)

    show_zero = filters.get("show_zero_balances")
    data = []
    for bucket in agg.values():
        if not show_zero and abs(bucket["balance_qty"]) < 1e-9:
            continue
        bucket["holder"] = _("Employee Custody") if bucket["employee"] else _("Building Store")
        bucket["value_sar"] = flt(bucket["balance_qty"]) * flt(bucket["unit_cost_sar"])
        data.append(bucket)

    data.sort(key=lambda d: (d["building"] or "", d["holder"], d["item_name"] or d["item"] or ""))
    return data
