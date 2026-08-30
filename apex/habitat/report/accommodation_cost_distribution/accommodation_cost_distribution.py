# Copyright (c) 2026, afmcoltd

import frappe
from frappe.utils import flt

from apex.apex_core.utils.report_summary import card, count_card, total_card


def execute(filters=None):
    columns = [
        {"label": frappe._("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": frappe._("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 160},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 150},
        {"label": frappe._("Ledger Type"), "fieldname": "ledger_type", "fieldtype": "Data", "width": 130},
        {"label": frappe._("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
        {"label": frappe._("Allocation Basis"), "fieldname": "allocation_basis", "fieldtype": "Data", "width": 120},
        {"label": frappe._("Source Type"), "fieldname": "source_doctype", "fieldtype": "Data", "width": 130},
        {"label": frappe._("Source Document"), "fieldname": "source_name", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Source Line ID"), "fieldname": "source_line_id", "fieldtype": "Data", "width": 140},
    ]

    filters = filters or {}

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if not (from_date and to_date):
        frappe.throw(frappe._("From Date and To Date are required."))

    query_filters = {
        "posting_mode": "Operational Memo",
        "posting_date": ["between", [from_date, to_date]],
    }
    if filters.get("building"):
        query_filters["building"] = filters["building"]
    if filters.get("project"):
        query_filters["project"] = filters["project"]
    if filters.get("company"):
        query_filters["company"] = filters["company"]
    if filters.get("cost_center"):
        query_filters["cost_center"] = filters["cost_center"]

    rows = frappe.get_all(
        "Accommodation Ledger",
        filters=query_filters,
        fields=[
            "posting_date",
            "employee",
            "building",
            "ledger_type",
            "employee_daily_share as amount",
            "allocation_basis",
            "source_doctype",
            "source_name",
            "source_line_id",
        ],
        order_by="posting_date desc",
        limit_page_length=0,
    )

    data = []
    for row in rows:
        data.append({
            "posting_date": row.posting_date,
            "employee": row.employee,
            "building": row.building,
            "ledger_type": row.ledger_type,
            "amount": flt(row.get("amount")),
            "allocation_basis": row.allocation_basis,
            "source_doctype": row.source_doctype,
            "source_name": row.source_name,
            "source_line_id": row.source_line_id,
        })

    summary = [
        count_card(frappe._("Ledger Entries"), data),
        total_card(frappe._("Amount"), data, "amount", "Currency"),
        card(frappe._("Employees"), len({r["employee"] for r in data if r.get("employee")}), "Int"),
        card(frappe._("Buildings"), len({r["building"] for r in data if r.get("building")}), "Int"),
    ]
    return columns, data, None, None, summary
