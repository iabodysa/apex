# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {"label": frappe._("Recovery Type"), "fieldname": "recovery_type", "fieldtype": "Data", "width": 200},
        {"label": frappe._("Count"), "fieldname": "count", "fieldtype": "Int", "width": 110},
        {"label": frappe._("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 160},
        {"label": frappe._("Total Recovered"), "fieldname": "total_recovered", "fieldtype": "Currency", "width": 160},
    ]

    query_filters = {}
    if filters:
        if filters.get("status"):
            query_filters["status"] = filters["status"]
        if filters.get("from_date") and filters.get("to_date"):
            query_filters["request_date"] = ["between", [filters["from_date"], filters["to_date"]]]
        elif filters.get("from_date"):
            query_filters["request_date"] = [">=", filters["from_date"]]
        elif filters.get("to_date"):
            query_filters["request_date"] = ["<=", filters["to_date"]]

    records = frappe.get_all(
        "Movement Cost Recovery",
        filters=query_filters,
        fields=["recovery_type", "amount", "status"],
    )

    summary = {}
    for row in records:
        rtype = row.get("recovery_type") or frappe._("Unspecified")
        bucket = summary.setdefault(
            rtype,
            {"recovery_type": rtype, "count": 0, "total_amount": 0.0, "total_recovered": 0.0},
        )
        bucket["count"] += 1
        amount = row.get("amount") or 0.0
        bucket["total_amount"] += amount
        if row.get("status") == "Recovered":
            bucket["total_recovered"] += amount

    data = sorted(summary.values(), key=lambda b: b["recovery_type"])

    return columns, data
