# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {"label": frappe._("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": frappe._("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 160},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 150},
        {"label": frappe._("Ledger Type"), "fieldname": "ledger_type", "fieldtype": "Data", "width": 130},
        {"label": frappe._("Amount (SAR)"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
    ]

    query_filters = {"posting_mode": "Operational Memo", "reversal_of": ["is", "not set"]}
    if filters and filters.get("building"):
        query_filters["building"] = filters["building"]

    data = frappe.get_all(
        "Accommodation Ledger",
        filters=query_filters,
        fields=[
            "posting_date",
            "employee",
            "building",
            "ledger_type",
            "employee_daily_share as amount",
        ],
        order_by="posting_date desc",
        limit_page_length=1000,
    )
    return columns, data
