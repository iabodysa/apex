# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {"label": frappe._("Settlement"), "fieldname": "name", "fieldtype": "Link", "options": "Rental Settlement", "width": 160},
        {"label": frappe._("Rental Office"), "fieldname": "rental_office", "fieldtype": "Link", "options": "Rental Office", "width": 180},
        {"label": frappe._("Period"), "fieldname": "period_month", "fieldtype": "Data", "width": 120},
        {"label": frappe._("Accrued Total"), "fieldname": "accrued_total", "fieldtype": "Currency", "width": 150},
        {"label": frappe._("Claimed Total"), "fieldname": "claimed_total", "fieldtype": "Currency", "width": 150},
        {"label": frappe._("Variance"), "fieldname": "variance", "fieldtype": "Currency", "width": 150},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
    ]

    query_filters = {}
    if filters:
        if filters.get("status"):
            query_filters["status"] = filters["status"]
        if filters.get("from_date") and filters.get("to_date"):
            query_filters["period_month"] = ["between", [filters["from_date"], filters["to_date"]]]
        elif filters.get("from_date"):
            query_filters["period_month"] = [">=", filters["from_date"]]
        elif filters.get("to_date"):
            query_filters["period_month"] = ["<=", filters["to_date"]]

    data = frappe.get_all(
        "Rental Settlement",
        filters=query_filters,
        fields=[
            "name",
            "rental_office",
            "period_month",
            "accrued_total",
            "claimed_total",
            "variance",
            "status",
        ],
        order_by="rental_office asc, period_month asc",
    )

    return columns, data
