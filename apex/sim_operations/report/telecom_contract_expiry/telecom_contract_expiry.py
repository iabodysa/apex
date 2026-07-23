# Copyright (c) 2026, AFMCO and contributors
"""Submitted telecom contracts expiring within a window, company-scoped."""

import frappe
from frappe.utils import add_days, date_diff, today

from apex.sim_operations import permissions


def execute(filters=None):
    filters = filters or {}
    columns = [
        {"label": frappe._("Contract"), "fieldname": "name", "fieldtype": "Link", "options": "Telecom Contract", "width": 180},
        {"label": frappe._("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
        {"label": frappe._("End Date"), "fieldname": "contract_end_date", "fieldtype": "Date", "width": 110},
        {"label": frappe._("Days to Expiry"), "fieldname": "days_to_expiry", "fieldtype": "Int", "width": 120},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": frappe._("SIMs"), "fieldname": "sim_count", "fieldtype": "Int", "width": 80},
        {"label": frappe._("Recurring Amount"), "fieldname": "recurring_amount", "fieldtype": "Currency", "options": "currency", "width": 140},
        {"label": frappe._("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 90},
    ]

    within_days = frappe.utils.cint(filters.get("within_days")) or 90
    query = {
        "docstatus": 1,
        "contract_end_date": ["<=", add_days(today(), within_days)],
    }
    if filters.get("company"):
        query["company"] = filters["company"]
    if filters.get("supplier"):
        query["supplier"] = filters["supplier"]

    restrict, allowed = permissions.report_company_scope(frappe.session.user)
    if restrict:
        if not allowed:
            return columns, []
        chosen = query.get("company")
        if chosen and chosen not in allowed:
            return columns, []
        if not chosen:
            query["company"] = ["in", allowed]

    data = frappe.get_all(
        "Telecom Contract",
        filters=query,
        fields=[
            "name",
            "supplier",
            "contract_end_date",
            "status",
            "sim_count",
            "recurring_amount",
            "currency",
        ],
        order_by="contract_end_date asc",
    )
    for row in data:
        row["days_to_expiry"] = (
            date_diff(row.contract_end_date, today()) if row.contract_end_date else None
        )
    return columns, data
