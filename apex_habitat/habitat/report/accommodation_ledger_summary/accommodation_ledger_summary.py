# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 160},
        {"label": frappe._("Ledger Type"), "fieldname": "ledger_type", "fieldtype": "Data", "width": 130},
        {"label": frappe._("Posting Mode"), "fieldname": "posting_mode", "fieldtype": "Data", "width": 130},
        {"label": frappe._("Allocation Basis"), "fieldname": "allocation_basis", "fieldtype": "Data", "width": 130},
        {"label": frappe._("Period Start"), "fieldname": "period_start", "fieldtype": "Date", "width": 110},
        {"label": frappe._("Period End"), "fieldname": "period_end", "fieldtype": "Date", "width": 110},
        {"label": frappe._("Total Site Cost (SAR)"), "fieldname": "total_site_cost", "fieldtype": "Currency", "width": 150},
        {"label": frappe._("Employee Daily Share (SAR)"), "fieldname": "employee_daily_share", "fieldtype": "Currency", "width": 170},
        {"label": frappe._("Source"), "fieldname": "source_name", "fieldtype": "Data", "width": 140},
    ]

    query_filters = {}
    if filters.get("building"):
        query_filters["building"] = filters["building"]
    if filters.get("ledger_type"):
        query_filters["ledger_type"] = filters["ledger_type"]
    if filters.get("from_date") and filters.get("to_date"):
        query_filters["posting_date"] = ["between", [filters["from_date"], filters["to_date"]]]
    elif filters.get("from_date"):
        query_filters["posting_date"] = [">=", filters["from_date"]]
    elif filters.get("to_date"):
        query_filters["posting_date"] = ["<=", filters["to_date"]]

    rows = frappe.get_all(
        "Accommodation Ledger",
        filters=query_filters,
        fields=[
            "building", "ledger_type", "posting_mode", "allocation_basis",
            "allocation_period_start as period_start", "allocation_period_end as period_end",
            "total_site_cost", "employee_daily_share", "source_doctype", "source_name",
        ],
        order_by="building asc, ledger_type asc, allocation_period_start desc",
        limit_page_length=5000,
    )

    data = []
    for row in rows:
        data.append({
            "building": row.building,
            "ledger_type": row.ledger_type,
            "posting_mode": row.posting_mode or "",
            "allocation_basis": row.allocation_basis or "",
            "period_start": row.period_start,
            "period_end": row.period_end,
            "total_site_cost": flt(row.total_site_cost),
            "employee_daily_share": flt(row.employee_daily_share),
            "source_name": row.source_name or "",
        })

    return columns, data
