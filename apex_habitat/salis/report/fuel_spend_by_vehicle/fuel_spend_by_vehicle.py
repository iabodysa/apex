# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

"""Fuel Spend by Vehicle - per-vehicle fuel litres and amount, derived from the
system-written Fuel Consumption Ledger (which itself consolidates Fuel Daily Log
and done Fuel Request records).

Aggregates ledger rows in the chosen window: total litres, total amount, an
average cost per litre, and the count of contributing ledger rows. It is
defensive about the source DocType: if Fuel Consumption Ledger is not migrated
yet, the report returns an empty data set rather than raising.

Optional filters: vehicle, period_month (YYYY-MM exact match).
"""

import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 200},
        {"label": _("Total Litres"), "fieldname": "total_litres", "fieldtype": "Float", "width": 130},
        {"label": _("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 150},
        {"label": _("Avg Cost / Litre"), "fieldname": "avg_cost_per_litre", "fieldtype": "Currency", "width": 150},
        {"label": _("Ledger Rows"), "fieldname": "row_count", "fieldtype": "Int", "width": 120},
    ]

    if not frappe.db.exists("DocType", "Fuel Consumption Ledger"):
        return columns, []

    query_filters = {}
    if filters.get("vehicle"):
        query_filters["vehicle"] = filters["vehicle"]
    if filters.get("period_month"):
        query_filters["period_month"] = filters["period_month"]

    rows = frappe.get_all(
        "Fuel Consumption Ledger",
        filters=query_filters,
        fields=["vehicle", "litres", "amount"],
    )

    summary = {}
    for entry in rows:
        vehicle = entry.get("vehicle") or ""
        bucket = summary.setdefault(
            vehicle,
            {"vehicle": vehicle, "total_litres": 0.0, "total_amount": 0.0, "row_count": 0},
        )
        bucket["total_litres"] += entry.get("litres") or 0.0
        bucket["total_amount"] += entry.get("amount") or 0.0
        bucket["row_count"] += 1

    data = []
    for bucket in summary.values():
        litres = bucket["total_litres"]
        bucket["avg_cost_per_litre"] = round(bucket["total_amount"] / litres, 3) if litres else 0.0
        data.append(bucket)

    data.sort(key=lambda r: r["total_amount"], reverse=True)

    return columns, data
