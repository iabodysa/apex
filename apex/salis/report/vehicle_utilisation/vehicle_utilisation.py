# Copyright (c) 2026, afmcoltd


import frappe
from frappe import _
from frappe.utils import flt

from apex.apex_core.utils.report_helpers import date_range_condition
from apex.apex_core.utils.report_summary import count_card, percent_card, total_card


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 200},
        {"label": _("Snapshots"), "fieldname": "snapshots", "fieldtype": "Int", "width": 100},
        {"label": _("Trips"), "fieldname": "trips_count", "fieldtype": "Int", "width": 100},
        {"label": _("Idle Days"), "fieldname": "idle_days", "fieldtype": "Int", "width": 110},
        {"label": _("Period Days"), "fieldname": "period_days", "fieldtype": "Int", "width": 120},
        {"label": _("Avg Utilisation %"), "fieldname": "utilisation_pct", "fieldtype": "Percent", "width": 150},
    ]

    if not frappe.db.exists("DocType", "Vehicle Utilisation Snapshot"):
        return columns, []

    query_filters = {}
    if filters.get("vehicle"):
        query_filters["vehicle"] = filters["vehicle"]
    date_condition = date_range_condition(filters, "snapshot_date")
    if date_condition is not None:
        query_filters["snapshot_date"] = date_condition

    snapshots = frappe.get_list(
        "Vehicle Utilisation Snapshot",
        filters=query_filters,
        fields=["vehicle", "period_days", "trips_count", "idle_days", "utilisation_pct"],
    )

    summary = {}
    for snap in snapshots:
        vehicle = snap.get("vehicle") or ""
        row = summary.setdefault(
            vehicle,
            {
                "vehicle": vehicle,
                "snapshots": 0,
                "trips_count": 0,
                "idle_days": 0,
                "period_days": 0,
                "_util_sum": 0.0,
            },
        )
        row["snapshots"] += 1
        row["trips_count"] += snap.get("trips_count") or 0
        row["idle_days"] += snap.get("idle_days") or 0
        row["period_days"] += snap.get("period_days") or 0
        row["_util_sum"] += snap.get("utilisation_pct") or 0.0

    data = []
    for row in summary.values():
        util_sum = row.pop("_util_sum")
        n = row["snapshots"]
        row["utilisation_pct"] = round(util_sum / n, 1) if n else 0.0
        data.append(row)

    data.sort(key=lambda r: r["vehicle"])

    idle = sum(flt(r.get("idle_days")) for r in data)
    period = sum(flt(r.get("period_days")) for r in data)
    summary = [
        count_card(_("Vehicles"), data),
        total_card(_("Trips"), data, "trips_count", "Int"),
        total_card(_("Idle Days"), data, "idle_days", "Int", indicator="Orange" if idle else None),
        percent_card(_("Idle Share"), idle, period),
    ]
    return columns, data, None, None, summary
