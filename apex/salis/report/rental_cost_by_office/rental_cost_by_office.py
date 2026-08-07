# Copyright (c) 2026, afmcoltd

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
from frappe.utils import flt

from apex.apex_core.utils.report_helpers import date_range_condition
from apex.apex_core.utils.report_summary import percent_card, total_card


def execute(filters=None):
    """Returns the columns, per-office accrued rental totals and summary cards for the report."""
    filters = filters or {}

    columns = [
        {"label": _("Rental Office"), "fieldname": "rental_office", "fieldtype": "Link", "options": "Rental Office", "width": 200},
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 160},
        {"label": _("Vehicles"), "fieldname": "vehicles", "fieldtype": "Int", "width": 100},
        {"label": _("Accrual Rows"), "fieldname": "row_count", "fieldtype": "Int", "width": 120},
        {"label": _("Total Accrued"), "fieldname": "total_accrued", "fieldtype": "Currency", "width": 150},
        {"label": _("Settled"), "fieldname": "settled_amount", "fieldtype": "Currency", "width": 150},
        {"label": _("Outstanding"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 150},
    ]

    if not frappe.db.exists("DocType", "Rental Accrual Ledger"):
        return columns, []

    query_filters = {}
    if filters.get("company"):
        query_filters["company"] = filters["company"]
    if filters.get("rental_office"):
        query_filters["rental_office"] = filters["rental_office"]
    if filters.get("vehicle"):
        query_filters["vehicle"] = filters["vehicle"]
    date_condition = date_range_condition(filters, "accrual_date")
    if date_condition is not None:
        query_filters["accrual_date"] = date_condition

    rows = frappe.get_all(
        "Rental Accrual Ledger",
        filters=query_filters,
        fields=["rental_office", "company", "vehicle", "amount", "settled"],
    )

    summary = {}
    for entry in rows:
        office = entry.get("rental_office") or ""
        bucket = summary.setdefault(
            office,
            {
                "rental_office": office,
                "company": entry.get("company") or "",
                "vehicles": 0,
                "row_count": 0,
                "total_accrued": 0.0,
                "settled_amount": 0.0,
                "outstanding_amount": 0.0,
                "_vehicles": set(),
            },
        )
        if not bucket["company"] and entry.get("company"):
            bucket["company"] = entry["company"]
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

    accrued = sum(flt(r.get("total_accrued")) for r in data)
    settled = sum(flt(r.get("settled_amount")) for r in data)
    summary = [
        total_card(_("Vehicles"), data, "vehicles", "Int"),
        total_card(_("Accrued"), data, "total_accrued", "Currency"),
        total_card(_("Settled"), data, "settled_amount", "Currency"),
        percent_card(_("Settled Share"), settled, accrued),
    ]
    return columns, data, None, None, summary
