# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

import frappe


def execute(filters=None):
    columns = [
        {"label": frappe._("Settlement"), "fieldname": "name", "fieldtype": "Link", "options": "Rental Settlement", "width": 180},
        {"label": frappe._("Rental Office"), "fieldname": "rental_office", "fieldtype": "Link", "options": "Rental Office", "width": 180},
        {"label": frappe._("Period"), "fieldname": "period_month", "fieldtype": "Data", "width": 110},
        {"label": frappe._("Accrued Total"), "fieldname": "accrued_total", "fieldtype": "Currency", "width": 140},
        {"label": frappe._("Claimed Total"), "fieldname": "claimed_total", "fieldtype": "Currency", "width": 140},
        {"label": frappe._("Variance"), "fieldname": "variance", "fieldtype": "Currency", "width": 130},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
    ]

    query_filters = {}
    if filters:
        for field in ("rental_office", "status", "period_month", "company"):
            if filters.get(field):
                query_filters[field] = filters[field]
        if filters.get("from_date") and filters.get("to_date"):
            query_filters["creation"] = ["between", [filters["from_date"], filters["to_date"]]]
        elif filters.get("from_date"):
            query_filters["creation"] = [">=", filters["from_date"]]
        elif filters.get("to_date"):
            query_filters["creation"] = ["<=", filters["to_date"]]

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
            "creation",
        ],
        order_by="creation desc",
    )

    return columns, data, None, _build_chart(data)


def _build_chart(data):
    """Bar chart of accrued-vs-claimed variance per rental office.

    Ported from the merged variance twin report, which duplicated this
    register's columns and only added this chart.
    """
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
