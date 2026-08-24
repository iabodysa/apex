# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, today

from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int
from apex.salis.api.dispatch_board import _permitted_projects
from apex.salis.tasks.common import (
    _queue_document,
    _reconcile_queue,
)

_ROW_SAVEPOINT = "salis_workshop_row"


def _overstay_stops() -> list:
    days = get_salis_int("workshop_overstay_days", 14)
    cutoff = add_days(today(), -days)
    rows = frappe.get_all(
        "Vehicle Suspension",
        filters={
            "stop_reason": "Maintenance",
            "docstatus": 1,
            "return_date": ["is", "not set"],
            "stop_date": ["<=", cutoff],
        },
        fields=["name", "vehicle", "stop_date"],
    )
    vehicle_ids = {r.vehicle for r in rows if r.vehicle}
    statuses = (
        {
            v["name"]: v["status"]
            for v in frappe.get_all(
                "Salis Vehicle", filters={"name": ["in", list(vehicle_ids)]}, fields=["name", "status"]
            )
        }
        if vehicle_ids
        else {}
    )
    return [
        r
        for r in rows
        if r.vehicle and statuses.get(r.vehicle) in ("Stopped", "Under Maintenance")
    ]


def workshop_overstay_watch() -> None:
    days = get_salis_int("workshop_overstay_days", 14)
    logger = frappe.logger()
    still_overstaying: list[str] = []
    for r in _overstay_stops():
        frappe.db.savepoint(_ROW_SAVEPOINT)
        try:
            msg = _("Vehicle {0} has been in the workshop since {1} (over {2} days).").format(
                r.vehicle, r.stop_date, days
            )
            logger.warning(
                f"workshop_overstay_watch: vehicle {r.vehicle} in workshop since "
                f"{r.stop_date} (over {days} days)."
            )
            _queue_document(
                "Vehicle Suspension", r.name, "Warning", msg, vehicle=r.vehicle,
            )
            still_overstaying.append(r.name)
        except Exception:
            frappe.db.rollback(save_point=_ROW_SAVEPOINT)
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Workshop overstay watch failed for {r.name}"[:140],
            )

    _reconcile_queue("Vehicle Suspension", still_overstaying)


@frappe.whitelist()
def get_workshop_overstay_count(filters=None) -> dict:
    frappe.has_permission("Salis Vehicle", "read", throw=True)
    vehicles = {r.vehicle for r in _overstay_stops()}
    if not vehicles:
        return {"value": 0}
    unscoped, projects = _permitted_projects()
    v_filters = {"name": ["in", list(vehicles)]}
    if not unscoped:
        if not projects:
            return {"value": 0}
        v_filters["project"] = ["in", projects]
    return {"value": frappe.db.count("Salis Vehicle", v_filters)}
