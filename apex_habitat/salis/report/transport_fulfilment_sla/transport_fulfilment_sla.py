# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

"""Transport Fulfilment SLA - requested-versus-fulfilled and on-time service
levels, derived from the system-written Trip Fulfilment Ledger (one row per
completed Dispatch Trip) cross-referenced with Transport Request demand.

For each trip-date day in the window it reports the number of Transport Requests
raised that day (demand), the fulfilled trips logged that day, the distinct
requests actually served, the on-time fulfilled trips, and the on-time rate.
Both source DocTypes are guarded: a missing Trip Fulfilment Ledger yields an
empty data set, and request demand is simply reported as 0 if Transport Request
is not migrated.

Optional filters: vehicle, from_date / to_date (on trip_date / request day).
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate


def _date_range(field, filters):
    f = {}
    if filters.get("from_date") and filters.get("to_date"):
        f[field] = ["between", [filters["from_date"], filters["to_date"]]]
    elif filters.get("from_date"):
        f[field] = [">=", filters["from_date"]]
    elif filters.get("to_date"):
        f[field] = ["<=", filters["to_date"]]
    return f


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Trip Date"), "fieldname": "trip_date", "fieldtype": "Date", "width": 120},
        {"label": _("Requests Raised"), "fieldname": "requests_raised", "fieldtype": "Int", "width": 140},
        {"label": _("Fulfilled Trips"), "fieldname": "fulfilled_trips", "fieldtype": "Int", "width": 130},
        {"label": _("Requests Served"), "fieldname": "requests_served", "fieldtype": "Int", "width": 140},
        {"label": _("Workers Moved"), "fieldname": "workers_moved", "fieldtype": "Int", "width": 130},
        {"label": _("On Time"), "fieldname": "on_time_trips", "fieldtype": "Int", "width": 100},
        {"label": _("On-Time %"), "fieldname": "on_time_pct", "fieldtype": "Percent", "width": 120},
    ]

    if not frappe.db.exists("DocType", "Trip Fulfilment Ledger"):
        return columns, []

    ledger_filters = {}
    if filters.get("vehicle"):
        ledger_filters["vehicle"] = filters["vehicle"]
    ledger_filters.update(_date_range("trip_date", filters))

    rows = frappe.get_all(
        "Trip Fulfilment Ledger",
        filters=ledger_filters,
        fields=["trip_date", "transport_request", "worker_count", "on_time"],
    )

    summary = {}
    for entry in rows:
        raw_day = entry.get("trip_date")
        day = getdate(raw_day) if raw_day else None
        bucket = summary.setdefault(
            day,
            {
                "trip_date": day,
                "requests_raised": 0,
                "fulfilled_trips": 0,
                "requests_served": 0,
                "workers_moved": 0,
                "on_time_trips": 0,
                "on_time_pct": 0.0,
                "_served": set(),
            },
        )
        bucket["fulfilled_trips"] += 1
        bucket["workers_moved"] += entry.get("worker_count") or 0
        if entry.get("on_time"):
            bucket["on_time_trips"] += 1
        if entry.get("transport_request"):
            bucket["_served"].add(entry["transport_request"])

    # Demand side: Transport Requests raised per day (guarded; pickup_datetime is
    # the demand timestamp on Transport Request).
    demand = {}
    if frappe.db.exists("DocType", "Transport Request"):
        tr_filters = _date_range("pickup_datetime", filters)
        requests = frappe.get_all(
            "Transport Request",
            filters=tr_filters,
            fields=["pickup_datetime"],
        )
        for req in requests:
            pickup = req.get("pickup_datetime")
            if not pickup:
                continue
            day = getdate(pickup)
            demand[day] = demand.get(day, 0) + 1

    # Merge demand into days that may have no fulfilled trips yet.
    for day, count in demand.items():
        bucket = summary.setdefault(
            day,
            {
                "trip_date": day,
                "requests_raised": 0,
                "fulfilled_trips": 0,
                "requests_served": 0,
                "workers_moved": 0,
                "on_time_trips": 0,
                "on_time_pct": 0.0,
                "_served": set(),
            },
        )
        bucket["requests_raised"] = count

    data = []
    for bucket in summary.values():
        bucket["requests_served"] = len(bucket.pop("_served"))
        fulfilled = bucket["fulfilled_trips"]
        bucket["on_time_pct"] = round((bucket["on_time_trips"] / fulfilled) * 100, 1) if fulfilled else 0.0
        data.append(bucket)

    data.sort(key=lambda r: (r["trip_date"] is None, r["trip_date"] or getdate(nowdate())))

    return columns, data
