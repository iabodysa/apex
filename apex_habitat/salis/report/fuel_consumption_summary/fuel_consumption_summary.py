# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {"label": frappe._("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 180},
        {"label": frappe._("Total Litres"), "fieldname": "total_litres", "fieldtype": "Float", "width": 130},
        {"label": frappe._("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 150},
        {"label": frappe._("Log Count"), "fieldname": "log_count", "fieldtype": "Int", "width": 110},
    ]

    log_filters = {}
    if filters:
        if filters.get("from_date") and filters.get("to_date"):
            log_filters["log_date"] = ["between", [filters["from_date"], filters["to_date"]]]
        elif filters.get("from_date"):
            log_filters["log_date"] = [">=", filters["from_date"]]
        elif filters.get("to_date"):
            log_filters["log_date"] = ["<=", filters["to_date"]]

    logs = frappe.get_all(
        "Fuel Daily Log",
        filters=log_filters,
        fields=["vehicle", "litres", "amount"],
    )

    summary = {}
    for log in logs:
        vehicle = log.vehicle or ""
        row = summary.setdefault(vehicle, {"vehicle": vehicle, "total_litres": 0.0, "total_amount": 0.0, "log_count": 0})
        row["total_litres"] += log.litres or 0
        row["total_amount"] += log.amount or 0
        row["log_count"] += 1

    data = sorted(summary.values(), key=lambda row: row["vehicle"])

    return columns, data
