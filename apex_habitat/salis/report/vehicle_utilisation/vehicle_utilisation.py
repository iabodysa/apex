# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

"""Vehicle Utilisation - per-vehicle roll-up of trips, idle days and average
utilisation, derived from the system-written Vehicle Utilisation Snapshot.

The snapshot is a trailing-window memo (one row per vehicle per snapshot date),
so this report aggregates snapshots in the chosen window: it sums trips and idle
days and averages the utilisation percentage per vehicle. It is defensive about
the source DocType: if Vehicle Utilisation Snapshot is not migrated yet, the
report returns an empty data set rather than raising.

Optional filters: vehicle, from_date / to_date (applied to snapshot_date).
"""

import frappe
from frappe import _


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
    if filters.get("from_date") and filters.get("to_date"):
        query_filters["snapshot_date"] = ["between", [filters["from_date"], filters["to_date"]]]
    elif filters.get("from_date"):
        query_filters["snapshot_date"] = [">=", filters["from_date"]]
    elif filters.get("to_date"):
        query_filters["snapshot_date"] = ["<=", filters["to_date"]]

    snapshots = frappe.get_all(
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

    return columns, data
