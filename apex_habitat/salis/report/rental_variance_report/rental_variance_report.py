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

    filters = filters or {}
    query_filters = {}
    if filters:
        if filters.get("status"):
            query_filters["status"] = filters["status"]
        if filters.get("company"):
            query_filters["company"] = filters["company"]
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

    return columns, data, None, _build_chart(data)


def _build_chart(data):
    """Bar chart of accrued-vs-claimed variance per rental office."""
    if not data:
        return None
    by_office = {}
    for row in data:
        office = row.get("rental_office") or frappe._("Unspecified")
        by_office[office] = by_office.get(office, 0.0) + (row.get("variance") or 0.0)
    if not by_office:
        return None
    labels = sorted(by_office)
    values = [round(by_office[o], 2) for o in labels]
    return {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{"name": frappe._("Variance"), "values": values}],
        },
    }
