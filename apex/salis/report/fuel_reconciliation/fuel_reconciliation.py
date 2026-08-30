# Copyright (c) 2026, afmcoltd


import frappe
from frappe import _
from frappe.utils import flt

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

    rows = frappe.get_list(
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

    quota_keys = [key for key in groups if key[0] and key[1]]
    quota_map = {}
    if quota_keys:
        for quota in frappe.get_all(
            "Fuel Quota",
            filters={
                "vehicle": ["in", list({key[0] for key in quota_keys})],
                "period_month": ["in", list({key[1] for key in quota_keys})],
            },
            fields=["vehicle", "period_month", "monthly_litres"],
        ):
            quota_map[(quota.vehicle, quota.period_month)] = quota.monthly_litres or 0.0

    for key, agg in groups.items():
        vehicle, period_month = key
        if not vehicle or not period_month:
            continue
        agg["quota_litres"] = quota_map.get(key, 0.0)
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
