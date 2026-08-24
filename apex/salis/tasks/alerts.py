# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import add_days, today

from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int
from apex.salis.tasks.common import (
    _reconcile_queue,
)

_ROW_SAVEPOINT = "salis_alerts_row"


def reconcile_operations_alerts() -> None:
    today_str = today()
    logger = frappe.logger()

    idle_days = get_salis_int("idle_vehicle_days", 7)
    lead_days = get_salis_int("alert_lead_days", 30)
    idle_cutoff = add_days(today_str, -idle_days)

    DT = frappe.qb.DocType("Dispatch Trip")
    vehicles_with_recent_trip = {
        r["vehicle"]
        for r in (
            frappe.qb.from_(DT)
            .select(DT.vehicle)
            .where(DT.docstatus == 1)
            .where(DT.status.isin(["Dispatched", "Completed"]))
            .where(DT.trip_date >= idle_cutoff)
            .where(DT.vehicle.isnotnull())
            .groupby(DT.vehicle)
        ).run(as_dict=True)
    }

    horizon = add_days(today_str, lead_days)
    SVC = frappe.qb.DocType("Salis Vehicle Compliance")
    vehicles_with_open_compliance = {
        r["parent"]
        for r in (
            frappe.qb.from_(SVC)
            .select(SVC.parent)
            .distinct()
            .where(SVC.expiry_date.isnotnull())
            .where(SVC.expiry_date <= horizon)
        ).run(as_dict=True)
    }

    active_vehicles = set(
        frappe.get_all("Salis Vehicle", filters={"status": "Active"}, pluck="name")
    )
    vehicle_keep = (active_vehicles - vehicles_with_recent_trip) | (
        vehicles_with_open_compliance & active_vehicles
    )

    active_drivers = set(
        frappe.get_all("Salis Driver", filters={"status": "Active"}, pluck="name")
    )
    attended_today = {
        r["driver"]
        for r in frappe.get_all(
            "Driver Attendance",
            filters={"attendance_date": today_str, "docstatus": 1},
            fields=["driver"],
        )
        if r["driver"]
    }
    driver_keep = active_drivers - attended_today

    drained = 0
    for doctype, keep in (
        ("Salis Vehicle", vehicle_keep),
        ("Salis Driver", driver_keep),
    ):
        frappe.db.savepoint(_ROW_SAVEPOINT)
        try:
            drained += _reconcile_queue(doctype, keep)
        except Exception:
            frappe.db.rollback(save_point=_ROW_SAVEPOINT)
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Queue reconciliation failed for {doctype}"[:140],
            )

    logger.info(
        f"reconcile_operations_alerts: drained {drained} assignment(s) whose "
        f"condition has cleared."
    )
