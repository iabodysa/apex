# Copyright (c) 2026, afmcoltd

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
from frappe.utils import flt

from apex.apex_core.utils.report_helpers import scoped_names
from apex.salis import permissions
from apex.apex_core.utils.report_summary import card, count_card, total_card


def execute(filters=None):
    """Returns the columns, per-vehicle fuel spend rows, chart and summary cards for the report."""
    filters = filters or {}

    columns = [
        {"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 200},
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 160},
        {"label": _("Total Litres"), "fieldname": "total_litres", "fieldtype": "Float", "width": 130},
        {"label": _("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 150},
        {"label": _("Avg Cost / Litre"), "fieldname": "avg_cost_per_litre", "fieldtype": "Currency", "width": 150},
        {"label": _("Ledger Rows"), "fieldname": "row_count", "fieldtype": "Int", "width": 120},
    ]

    if not frappe.db.exists("DocType", "Fuel Consumption Ledger"):
        return columns, []

    query_filters = {}
    if filters.get("company"):
        query_filters["company"] = filters["company"]
    if filters.get("vehicle"):
        query_filters["vehicle"] = filters["vehicle"]
    if filters.get("period_month"):
        query_filters["period_month"] = filters["period_month"]

    restrict, allowed = permissions.report_project_scope(frappe.session.user, doctype="Fuel Consumption Ledger")
    if restrict:
        if not allowed:
            return columns, []
        in_scope_vehicles = scoped_names("Salis Vehicle", allowed)
        if not in_scope_vehicles:
            return columns, []
        query_filters["vehicle"] = ["in", in_scope_vehicles]

    rows = frappe.get_all(
        "Fuel Consumption Ledger",
        filters=query_filters,
        fields=["vehicle", "company", "litres", "amount"],
    )

    summary = {}
    for entry in rows:
        vehicle = entry.get("vehicle") or ""
        bucket = summary.setdefault(
            vehicle,
            {"vehicle": vehicle, "company": entry.get("company") or "", "total_litres": 0.0, "total_amount": 0.0, "row_count": 0},
        )
        if not bucket["company"] and entry.get("company"):
            bucket["company"] = entry["company"]
        bucket["total_litres"] += entry.get("litres") or 0.0
        bucket["total_amount"] += entry.get("amount") or 0.0
        bucket["row_count"] += 1

    data = []
    for bucket in summary.values():
        litres = bucket["total_litres"]
        bucket["avg_cost_per_litre"] = round(bucket["total_amount"] / litres, 3) if litres else 0.0
        data.append(bucket)

    data.sort(key=lambda r: r["total_amount"], reverse=True)

    litres = sum(flt(r.get("total_litres")) for r in data)
    amount = sum(flt(r.get("total_amount")) for r in data)
    summary = [
        count_card(_("Vehicles"), data),
        total_card(_("Total Litres"), data, "total_litres"),
        total_card(_("Total Amount"), data, "total_amount", "Currency"),
        card(_("Average Cost per Litre"), round(amount / litres, 2) if litres else 0.0, "Currency"),
    ]
    return columns, data, None, _build_chart(data), summary


def _build_chart(data):
    """Bar chart of total fuel spend for the highest-spend vehicles."""
    if not data:
        return None
    top = data[:10]
    labels = [r.get("vehicle") or _("Unspecified") for r in top]
    values = [round(r.get("total_amount") or 0.0, 2) for r in top]
    return {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{"name": _("Total Amount"), "values": values}],
        },
    }
