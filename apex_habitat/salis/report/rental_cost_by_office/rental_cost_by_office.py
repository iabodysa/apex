# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

"""Rental Cost by Office - accrued rental cost grouped by Rental Office, derived
from the machine-written Rental Accrual Ledger (one row per in-service rented
vehicle per day; posts no GL).

Aggregates accrual rows in the chosen window per office: total accrued amount,
the already-settled and still-outstanding portions, the count of distinct
vehicles, and the accrual-row count. It is defensive about the source DocType:
if Rental Accrual Ledger is not migrated yet, the report returns an empty data
set rather than raising.

Optional filters: rental_office, vehicle, from_date / to_date (on accrual_date).
"""

import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Rental Office"), "fieldname": "rental_office", "fieldtype": "Link", "options": "Rental Office", "width": 200},
        {"label": _("Vehicles"), "fieldname": "vehicles", "fieldtype": "Int", "width": 100},
        {"label": _("Accrual Rows"), "fieldname": "row_count", "fieldtype": "Int", "width": 120},
        {"label": _("Total Accrued"), "fieldname": "total_accrued", "fieldtype": "Currency", "width": 150},
        {"label": _("Settled"), "fieldname": "settled_amount", "fieldtype": "Currency", "width": 150},
        {"label": _("Outstanding"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 150},
    ]

    if not frappe.db.exists("DocType", "Rental Accrual Ledger"):
        return columns, []

    query_filters = {}
    if filters.get("rental_office"):
        query_filters["rental_office"] = filters["rental_office"]
    if filters.get("vehicle"):
        query_filters["vehicle"] = filters["vehicle"]
    if filters.get("from_date") and filters.get("to_date"):
        query_filters["accrual_date"] = ["between", [filters["from_date"], filters["to_date"]]]
    elif filters.get("from_date"):
        query_filters["accrual_date"] = [">=", filters["from_date"]]
    elif filters.get("to_date"):
        query_filters["accrual_date"] = ["<=", filters["to_date"]]

    rows = frappe.get_all(
        "Rental Accrual Ledger",
        filters=query_filters,
        fields=["rental_office", "vehicle", "amount", "settled"],
    )

    summary = {}
    for entry in rows:
        office = entry.get("rental_office") or ""
        bucket = summary.setdefault(
            office,
            {
                "rental_office": office,
                "vehicles": 0,
                "row_count": 0,
                "total_accrued": 0.0,
                "settled_amount": 0.0,
                "outstanding_amount": 0.0,
                "_vehicles": set(),
            },
        )
        amount = entry.get("amount") or 0.0
        bucket["row_count"] += 1
        bucket["total_accrued"] += amount
        if entry.get("settled"):
            bucket["settled_amount"] += amount
        else:
            bucket["outstanding_amount"] += amount
        if entry.get("vehicle"):
            bucket["_vehicles"].add(entry["vehicle"])

    data = []
    for bucket in summary.values():
        bucket["vehicles"] = len(bucket.pop("_vehicles"))
        data.append(bucket)

    data.sort(key=lambda r: r["total_accrued"], reverse=True)

    return columns, data
