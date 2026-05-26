# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {"label": frappe._("Payment"), "fieldname": "name", "fieldtype": "Link", "options": "Salis Payment Request", "width": 180},
        {"label": frappe._("Expense Type"), "fieldname": "expense_type", "fieldtype": "Data", "width": 150},
        {"label": frappe._("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 180},
        {"label": frappe._("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 180},
        {"label": frappe._("Requested By"), "fieldname": "requested_by", "fieldtype": "Data", "width": 160},
        {"label": frappe._("Finance Approved By"), "fieldname": "finance_approved_by", "fieldtype": "Data", "width": 160},
    ]

    query_filters = {}
    if filters:
        for field in ("status", "expense_type"):
            if filters.get(field):
                query_filters[field] = filters[field]
        if filters.get("from_date") and filters.get("to_date"):
            query_filters["creation"] = ["between", [filters["from_date"], filters["to_date"]]]
        elif filters.get("from_date"):
            query_filters["creation"] = [">=", filters["from_date"]]
        elif filters.get("to_date"):
            query_filters["creation"] = ["<=", filters["to_date"]]

    data = frappe.get_all(
        "Salis Payment Request",
        filters=query_filters,
        fields=[
            "name",
            "expense_type",
            "amount",
            "status",
            "supplier",
            "project",
            "requested_by",
            "finance_approved_by",
            "creation",
        ],
        order_by="creation desc",
    )

    return columns, data
