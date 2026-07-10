# Copyright (c) 2026, AFMCO and contributors
"""Custody Outstanding by Worker — what each worker currently holds in custody,
derived from the read-only Accommodation Stock Ledger.

A worker-first specialization of Accommodation Stock Balance: only Custody Article
rows with an employee set (i.e. in someone's custody, not building store) are
counted. Balance = sum(signed qty) of non-cancelled rows up to the as-on date,
grouped by employee + building + article — issue rows add, return rows reverse, so
the net is the live outstanding holding. Value = balance * unit cost."""

import frappe
from frappe import _
from frappe.utils import flt, today

from apex_habitat.habitat import permissions


def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 180},
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 170},
        {"label": _("Article"), "fieldname": "item", "fieldtype": "Link", "options": "Custody Article", "width": 150},
        {"label": _("Article Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
        {"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 80},
        {"label": _("Outstanding Qty"), "fieldname": "balance_qty", "fieldtype": "Float", "width": 130},
        {"label": _("Unit Cost (SAR)"), "fieldname": "unit_cost", "fieldtype": "Currency", "width": 130},
        {"label": _("Outstanding Value (SAR)"), "fieldname": "value_sar", "fieldtype": "Currency", "width": 150},
    ]


def get_data(filters):
    conditions = {
        "is_cancelled": 0,
        "item_type": "Custody Article",
        "employee": ["is", "set"],
        "posting_date": ["<=", filters.get("as_on_date") or today()],
    }
    if filters.get("employee"):
        conditions["employee"] = filters["employee"]
    if filters.get("building"):
        conditions["building"] = filters["building"]

    # get_all forces ignore_permissions, bypassing the building row-scoping the desk
    # list gets via permission_query_conditions — re-apply the caller's building scope
    # (Accommodation Stock Ledger carries a direct building); oversight roles see all.
    user = frappe.session.user
    if not permissions._building_is_unscoped(user):
        allowed = permissions._allowed_buildings(user)
        if not allowed:
            return []
        chosen = conditions.get("building")
        if chosen and chosen not in allowed:
            return []
        if not chosen:
            conditions["building"] = ["in", allowed]

    rows = frappe.get_all(
        "Accommodation Stock Ledger",
        filters=conditions,
        fields=["employee", "building", "item", "item_name", "uom", "signed_qty", "unit_cost"],
    )

    agg = {}
    for r in rows:
        key = (r.employee, r.building, r.item)
        bucket = agg.setdefault(key, {
            "employee": r.employee, "building": r.building, "item": r.item,
            "item_name": r.item_name, "uom": r.uom,
            "unit_cost": flt(r.unit_cost), "balance_qty": 0.0,
        })
        bucket["balance_qty"] += flt(r.signed_qty)
        if r.unit_cost:
            bucket["unit_cost"] = flt(r.unit_cost)

    show_zero = filters.get("show_zero_balances")
    data = []
    for bucket in agg.values():
        if not show_zero and abs(bucket["balance_qty"]) < 1e-9:
            continue
        bucket["value_sar"] = flt(bucket["balance_qty"]) * flt(bucket["unit_cost"])
        data.append(bucket)

    data.sort(key=lambda d: (d["employee"] or "", d["building"] or "", d["item_name"] or d["item"] or ""))
    return data
