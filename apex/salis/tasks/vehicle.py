# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Salis fleet module (split by domain)."""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count, Sum
from pypika import Case

from apex.salis.tasks.common import (
    BATCH_SIZE,
    _raise_alert,
    _settings_int,
)

# Constant name, re-issued each iteration: MariaDB replaces a same-named savepoint
# rather than stacking one per row. Distinct from _raise_alert's own name, which
# runs inside these loops.
_ROW_SAVEPOINT = "salis_vehicle_row"


def idle_vehicle_watch() -> None:
    """Flag Active vehicles with no dispatch trip in the last ``idle_vehicle_days``.

    A vehicle is idle if it has no submitted Dispatch Trip (status
    Dispatched/Completed) on or after the cutoff (``idle_vehicle_days``; Salis
    Settings, default 7). Previously this ran one ``get_all`` per vehicle (N+1);
    now a single grouped query returns the set of vehicles WITH a recent trip,
    and the idle set is the difference in memory — same behaviour, one DB round
    trip for the trip data instead of one per vehicle.
    """
    from frappe.utils import add_days, today

    today_str = today()
    logger = frappe.logger()
    idle_days = _settings_int("idle_vehicle_days", 7)
    cutoff = add_days(today_str, -idle_days)

    # [#r94w3h]
    try:
        DT = frappe.qb.DocType("Dispatch Trip")
        rows = (
            frappe.qb.from_(DT)
            .select(DT.vehicle)
            .where(DT.docstatus == 1)
            .where(DT.status.isin(["Dispatched", "Completed"]))
            .where(DT.trip_date >= cutoff)
            .where(DT.vehicle.isnotnull())
            .groupby(DT.vehicle)
        ).run(as_dict=True)
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Idle vehicle watch: recent-trip aggregate failed"[:140],
        )
        return
    vehicles_with_recent_trip = {r["vehicle"] for r in rows}

    start = 0
    while True:
        vehicles = frappe.get_all(
            "Salis Vehicle",
            filters={"status": "Active"},
            fields=["name"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not vehicles:
            break

        for v in vehicles:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                if v.name in vehicles_with_recent_trip:
                    continue
                # [#q9q3e3]
                msg = (f"idle_vehicle_watch: vehicle {v.name} has had no dispatch "
                       f"trip in the last {idle_days} days.")
                logger.warning(msg)
                _raise_alert("Idle Vehicle", "Info", msg,
                             "Salis Vehicle", v.name, vehicle=v.name)
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Idle vehicle watch failed for {v.name}"[:140],
                )

        start += BATCH_SIZE


def vehicle_compliance_expiry_watch() -> None:
    """Alert on vehicle compliance documents at or past their expiry window.

    Reads Salis Vehicle Compliance child rows whose ``expiry_date`` is within
    ``alert_lead_days`` (Salis Settings; default 30) of today. For each row
    raises a "License Expiry" alert referencing the parent vehicle and
    compliance type — Critical if already expired, otherwise Warning. Per-row
    de-dup is handled by ``_raise_alert`` (one Open alert per vehicle+type+day).
    """
    from frappe.utils import add_days, getdate, today

    today_str = today()
    today_date = getdate(today_str)
    logger = frappe.logger()
    lead_days = _settings_int("alert_lead_days", 30)
    horizon = add_days(today_str, lead_days)

    start = 0
    while True:
        rows = frappe.get_all(
            "Salis Vehicle Compliance",
            filters={"expiry_date": ["<=", horizon]},
            fields=["parent", "compliance_type", "expiry_date"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not rows:
            break

        for c in rows:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                expired = bool(c.expiry_date) and getdate(c.expiry_date) < today_date
                severity = "Critical" if expired else "Warning"
                state = "expired on" if expired else "expires on"
                msg = (f"vehicle_compliance_expiry_watch: vehicle {c.parent} "
                       f"{c.compliance_type} compliance {state} {c.expiry_date}.")
                logger.warning(msg)
                _raise_alert("License Expiry", severity, msg,
                             "Salis Vehicle", c.parent, vehicle=c.parent)
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Vehicle compliance watch failed for {c.parent}"[:140],
                )

        start += BATCH_SIZE


def vehicle_utilization_summary() -> None:
    """Write a trailing-7-day utilisation summary per Active vehicle.

    For each Active vehicle, aggregates the count of Dispatch Trips and the
    distance (sum of ``odometer_end - odometer_start``) over the last 7 days and
    logs the result. Vehicles with zero trips additionally get an Info
    "Idle Vehicle" alert as a weekly recap (the actionable output, idempotent per
    day via the alert dedupe).
    """
    from frappe.utils import add_days, today

    today_str = today()
    window_start = add_days(today_str, -7)
    logger = frappe.logger()

    # [#gdp7wq]
    try:
        DT = frappe.qb.DocType("Dispatch Trip")
        distance_expr = Sum(
            Case()
            .when(DT.odometer_end > DT.odometer_start, DT.odometer_end - DT.odometer_start)
            .else_(0)
        )
        agg_rows = (
            frappe.qb.from_(DT)
            .select(
                DT.vehicle,
                Count(DT.name).as_("trip_count"),
                distance_expr.as_("distance"),
            )
            .where(DT.docstatus == 1)
            .where(DT.status.isin(["Dispatched", "Completed"]))
            .where(DT.trip_date.between(window_start, today_str))
            .where(DT.vehicle.isnotnull())
            .groupby(DT.vehicle)
        ).run(as_dict=True)
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Vehicle utilisation summary: trip aggregate failed"[:140],
        )
        return
    util_by_vehicle = {
        r["vehicle"]: (int(r["trip_count"] or 0), int(r["distance"] or 0))
        for r in agg_rows
    }

    start = 0
    while True:
        vehicles = frappe.get_all(
            "Salis Vehicle",
            filters={"status": "Active"},
            fields=["name"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not vehicles:
            break

        for v in vehicles:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                trip_count, distance = util_by_vehicle.get(v.name, (0, 0))

                # [#rsz9o4]
                logger.info(
                    f"vehicle_utilization_summary: {v.name} — {trip_count} trips, "
                    f"{distance} km over the last 7 days."
                )

                if trip_count == 0:
                    msg = (f"vehicle_utilization_summary: vehicle {v.name} logged no "
                           f"dispatch trips in the last 7 days.")
                    _raise_alert("Idle Vehicle", "Info", msg,
                                 "Salis Vehicle", v.name, vehicle=v.name)
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Vehicle utilisation summary failed for {v.name}"[:140],
                )

        start += BATCH_SIZE

    logger.info("vehicle_utilization_summary: weekly summaries written.")
