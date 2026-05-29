# Copyright (c) 2026, AFMCO and contributors
"""Occupancy Trend — historical per-building occupancy from the read-only
Accommodation Occupancy Snapshot engine (min/avg/max occupancy, days over
capacity). Answers questions the live occupancy_percent field cannot, since it
keeps no history."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today


def execute(filters=None):
    filters = filters or {}
    rows = _fetch_rows(filters)
    data = get_data(rows)
    return get_columns(), data, None, _build_chart(rows)


def get_columns():
    return [
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 200},
        {"label": _("Snapshots"), "fieldname": "snapshots", "fieldtype": "Int", "width": 100},
        {"label": _("Min Occupancy %"), "fieldname": "min_occ", "fieldtype": "Percent", "width": 140},
        {"label": _("Avg Occupancy %"), "fieldname": "avg_occ", "fieldtype": "Percent", "width": 140},
        {"label": _("Max Occupancy %"), "fieldname": "max_occ", "fieldtype": "Percent", "width": 140},
        {"label": _("Days Over Capacity"), "fieldname": "days_over", "fieldtype": "Int", "width": 150},
        {"label": _("Avg Available Capacity"), "fieldname": "avg_avail", "fieldtype": "Float", "width": 180},
    ]


def _fetch_rows(filters):
    to_date = filters.get("to_date") or today()
    from_date = filters.get("from_date") or add_days(getdate(to_date), -30)
    conditions = {"snapshot_date": ["between", [from_date, to_date]]}
    if filters.get("building"):
        conditions["building"] = filters["building"]

    return frappe.get_all(
        "Accommodation Occupancy Snapshot",
        filters=conditions,
        fields=["building", "snapshot_date", "occupancy_percent", "available_capacity"],
        order_by="snapshot_date asc, building asc",
    )


def get_data(rows):
    agg = {}
    for r in rows:
        a = agg.setdefault(r.building, {"occ": [], "avail": [], "over": 0})
        occ = flt(r.occupancy_percent)
        a["occ"].append(occ)
        a["avail"].append(flt(r.available_capacity))
        if occ > 100:
            a["over"] += 1

    data = []
    for building, a in agg.items():
        occ = a["occ"] or [0]
        avail = a["avail"] or [0]
        data.append({
            "building": building,
            "snapshots": len(a["occ"]),
            "min_occ": flt(min(occ), 2),
            "avg_occ": flt(sum(occ) / len(occ), 2),
            "max_occ": flt(max(occ), 2),
            "days_over": a["over"],
            "avg_avail": flt(sum(avail) / len(avail), 2),
        })
    return sorted(data, key=lambda x: x["building"])


def _build_chart(rows):
    """Line chart of average occupancy % across all buildings, per snapshot date."""
    if not rows:
        return None
    by_date = {}
    for r in rows:
        day = r.get("snapshot_date")
        if not day:
            continue
        by_date.setdefault(str(day), []).append(flt(r.occupancy_percent))
    if not by_date:
        return None
    labels = sorted(by_date)
    values = [flt(sum(by_date[d]) / len(by_date[d]), 2) for d in labels]
    return {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{"name": _("Avg Occupancy %"), "values": values}],
        },
    }
