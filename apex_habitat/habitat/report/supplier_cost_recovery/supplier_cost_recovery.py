# Copyright (c) 2026, AFMCO and contributors
"""Supplier Cost Recovery — monthly aggregation of external-supplier accommodation
costs from the Accommodation Ledger, with an operational markup applied dynamically
from Habitat Settings.

The ledger is written daily (one set of rows per housed day, so check-ins/outs are
exact); this report rolls those daily rows up into a monthly per-supplier total.
"""

import calendar

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Supplier"), "fieldname": "billed_to_supplier", "fieldtype": "Link", "options": "Supplier", "width": 180},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 160},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 150},
        {"label": _("Days Housed"), "fieldname": "days_housed", "fieldtype": "Int", "width": 110},
        {"label": _("Base Accommodation Cost"), "fieldname": "base_cost", "fieldtype": "Currency", "width": 180},
        {"label": _("Operational Markup"), "fieldname": "markup", "fieldtype": "Currency", "width": 160},
        {"label": _("Total Deduction Amount"), "fieldname": "total_deduction", "fieldtype": "Currency", "width": 190},
    ]


def get_data(filters):
    today = getdate()
    month = int(filters.get("month") or today.month)
    year = int(filters.get("year") or today.year)
    last_day = calendar.monthrange(year, month)[1]
    from_date = f"{year}-{month:02d}-01"
    to_date = f"{year}-{month:02d}-{last_day:02d}"

    conditions = {
        "posting_date": ["between", [from_date, to_date]],
        "billed_to_supplier": ["is", "set"],
    }
    if filters.get("supplier"):
        conditions["billed_to_supplier"] = filters["supplier"]
    if filters.get("project"):
        conditions["project"] = filters["project"]
    if filters.get("company"):
        conditions["company"] = filters["company"]
    if filters.get("cost_center"):
        conditions["cost_center"] = filters["cost_center"]

    rows = frappe.get_all(
        "Accommodation Ledger",
        filters=conditions,
        fields=[
            "billed_to_supplier",
            "employee",
            "project",
            "count(distinct posting_date) as days_housed",
            "sum(employee_daily_share) as base_cost",
        ],
        group_by="billed_to_supplier, employee, project",
        order_by="billed_to_supplier asc, employee asc",
    )

    # Markup is applied dynamically from settings at report time (not stored).
    markup_enabled = frappe.db.get_single_value("Habitat Settings", "enable_supplier_markup")
    markup_pct = flt(frappe.db.get_single_value("Habitat Settings", "supplier_markup_percent")) if markup_enabled else 0.0

    data = []
    for r in rows:
        base = flt(r.base_cost)
        markup = flt(base * markup_pct / 100.0, 2)
        data.append({
            "billed_to_supplier": r.billed_to_supplier,
            "employee": r.employee,
            "project": r.project,
            "days_housed": r.days_housed,
            "base_cost": flt(base, 2),
            "markup": markup,
            "total_deduction": flt(base + markup, 2),
        })
    return data
