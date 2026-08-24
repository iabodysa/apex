# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_days, getdate, today
from pypika import Case

from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int
from apex.salis.tasks.common import (
    BATCH_SIZE,
    _queue_document,
)

_ROW_SAVEPOINT = "salis_vehicle_row"

def idle_vehicle_watch() -> None:
    today_str = today()
    logger = frappe.logger()
    idle_days = get_salis_int("idle_vehicle_days", 7)
    cutoff = add_days(today_str, -idle_days)

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
                log_msg = (f"idle_vehicle_watch: vehicle {v.name} has had no dispatch "
                           f"trip in the last {idle_days} days.")
                logger.warning(log_msg)
                _queue_document(
                    "Salis Vehicle",
                    v.name,
                    "Info",
                    _("Vehicle {0} has had no dispatch trip in the last {1} days.").format(
                        v.name, idle_days
                    ),
                    vehicle=v.name,
                )
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Idle vehicle watch failed for {v.name}"[:140],
                )

        start += BATCH_SIZE

def vehicle_compliance_expiry_watch() -> None:
    today_str = today()
    today_date = getdate(today_str)
    logger = frappe.logger()
    lead_days = get_salis_int("alert_lead_days", 30)
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
                log_msg = (f"vehicle_compliance_expiry_watch: vehicle {c.parent} "
                           f"{c.compliance_type} compliance {state} {c.expiry_date}.")
                logger.warning(log_msg)
                template = (
                    _("Vehicle {0}: {1} compliance expired on {2}.")
                    if expired
                    else _("Vehicle {0}: {1} compliance expires on {2}.")
                )
                _queue_document(
                    "Salis Vehicle",
                    c.parent,
                    severity,
                    template.format(
                        c.parent, _(c.compliance_type) if c.compliance_type else "", c.expiry_date
                    ),
                    vehicle=c.parent,
                )
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Vehicle compliance watch failed for {c.parent}"[:140],
                )

        start += BATCH_SIZE

def vehicle_utilization_summary() -> None:
    today_str = today()
    window_start = add_days(today_str, -7)
    logger = frappe.logger()

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

                logger.info(
                    f"vehicle_utilization_summary: {v.name} — {trip_count} trips, "
                    f"{distance} km over the last 7 days."
                )

                if trip_count == 0:
                    _queue_document(
                        "Salis Vehicle",
                        v.name,
                        "Info",
                        _("Vehicle {0} logged no dispatch trips in the last 7 days.").format(
                            v.name
                        ),
                        vehicle=v.name,
                    )
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Vehicle utilisation summary failed for {v.name}"[:140],
                )

        start += BATCH_SIZE

    logger.info("vehicle_utilization_summary: weekly summaries written.")
