# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

"""Fuel Reconciliation report.

ORM report grouping Fuel Consumption Ledger rows by vehicle + period (month):
total litres, total amount, the allocated quota litres (looked up from Fuel
Quota), and the variance (quota litres - consumed litres). A negative variance
means consumption exceeded the quota.
"""

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": frappe._("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 180},
        {"label": frappe._("Period"), "fieldname": "period_month", "fieldtype": "Data", "width": 100},
        {"label": frappe._("Total Litres"), "fieldname": "total_litres", "fieldtype": "Float", "width": 120},
        {"label": frappe._("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 140},
        {"label": frappe._("Quota Litres"), "fieldname": "quota_litres", "fieldtype": "Float", "width": 120},
        {"label": frappe._("Variance (L)"), "fieldname": "variance", "fieldtype": "Float", "width": 120},
    ]

    ledger_filters = {}
    if filters.get("vehicle"):
        ledger_filters["vehicle"] = filters["vehicle"]
    if filters.get("period_month"):
        ledger_filters["period_month"] = filters["period_month"]

    rows = frappe.get_all(
        "Fuel Consumption Ledger",
        filters=ledger_filters,
        fields=["vehicle", "period_month", "litres", "amount"],
    )

    # Group by (vehicle, period_month).
    groups = {}
    for row in rows:
        key = (row.vehicle or "", row.period_month or "")
        agg = groups.setdefault(
            key,
            {
                "vehicle": row.vehicle or "",
                "period_month": row.period_month or "",
                "total_litres": 0.0,
                "total_amount": 0.0,
                "quota_litres": 0.0,
                "variance": 0.0,
            },
        )
        agg["total_litres"] += row.litres or 0
        agg["total_amount"] += row.amount or 0

    # Look up the quota litres for each group and compute variance.
    quota_cache = {}
    for key, agg in groups.items():
        vehicle, period_month = key
        if not vehicle or not period_month:
            continue
        if key not in quota_cache:
            quota_cache[key] = (
                frappe.db.get_value(
                    "Fuel Quota",
                    {"vehicle": vehicle, "period_month": period_month},
                    "monthly_litres",
                )
                or 0.0
            )
        agg["quota_litres"] = quota_cache[key]
        agg["variance"] = (agg["quota_litres"] or 0.0) - agg["total_litres"]

    data = sorted(groups.values(), key=lambda r: (r["vehicle"], r["period_month"]))

    return columns, data, None, _build_chart(data)


def _build_chart(data):
    """Bar chart of the largest fuel variance (quota - consumed) per vehicle/period."""
    if not data:
        return None
    ranked = sorted(data, key=lambda r: abs(r.get("variance") or 0.0), reverse=True)[:10]
    if not ranked:
        return None
    labels = [f"{r['vehicle']} {r['period_month']}".strip() for r in ranked]
    values = [round(r.get("variance") or 0.0, 2) for r in ranked]
    return {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{"name": frappe._("Variance (L)"), "values": values}],
        },
    }
