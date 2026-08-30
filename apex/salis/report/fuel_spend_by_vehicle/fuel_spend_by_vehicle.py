# Copyright (c) 2026, afmcoltd


import frappe
from frappe import _
from frappe.utils import flt

from apex.apex_core.utils.report_summary import card, count_card, total_card


def execute(filters=None):
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

    rows = frappe.get_list(
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
