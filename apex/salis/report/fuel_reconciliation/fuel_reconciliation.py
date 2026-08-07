# Copyright (c) 2026, AFMCO and contributors

"""Fuel Reconciliation report.

ORM report grouping Fuel Consumption Ledger rows by vehicle + period (month):
total litres, total amount, the allocated quota litres (looked up from Fuel
Quota), and the variance (quota litres - consumed litres). A negative variance
means consumption exceeded the quota.
"""

import frappe
from frappe import _
from frappe.utils import flt

from apex.apex_core.utils.report_helpers import scoped_names
from apex.salis import permissions
from apex.apex_core.utils.report_summary import count_card, total_card


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

    restrict, allowed = permissions.report_project_scope(frappe.session.user)
    if restrict:
        if not allowed:
            return columns, []
        in_scope_vehicles = scoped_names("Salis Vehicle", allowed)
        if not in_scope_vehicles:
            return columns, []
        ledger_filters["vehicle"] = ["in", in_scope_vehicles]

    rows = frappe.get_all(
        "Fuel Consumption Ledger",
        filters=ledger_filters,
        fields=["vehicle", "period_month", "litres", "amount"],
    )

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

    variance = sum(flt(r.get("variance")) for r in data)
    summary = [
        count_card(_("Rows"), data),
        total_card(_("Total Litres"), data, "total_litres"),
        total_card(_("Total Amount"), data, "total_amount", "Currency"),
        total_card(_("Variance"), data, "variance", indicator="Red" if variance < 0 else "Green"),
    ]
    return columns, data, None, _build_chart(data), summary


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
