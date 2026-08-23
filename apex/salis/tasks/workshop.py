# Copyright (c) 2026, afmcoltd
"""Scheduled tasks for the Salis fleet module (split by domain)."""

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
    """Submitted Maintenance Vehicle Suspensions still open past the overstay cutoff,
    for vehicles still out of service.

    A vehicle is overstaying if it is still Stopped / Under Maintenance and
    carries a submitted Vehicle Suspension (reason Maintenance) with no ``return_date``
    whose ``stop_date`` is on or before the cutoff (``workshop_overstay_days``;
    Salis Settings, default 14). Shared by ``workshop_overstay_watch`` (the alert)
    and ``get_workshop_overstay_count`` (the number card) so the rule cannot drift
    between them. Returns the Vehicle Suspension rows (name, vehicle, stop_date).
    """
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
    """Flag vehicles in the workshop longer than ``workshop_overstay_days``.

    Each overstaying stop (see ``_overstay_stops`` for the rule) is ASSIGNED to the
    Fleet Supervisor queue — the Vehicle Suspension is the document the supervisor
    closes to release the vehicle — and the queue is reconciled at the end of the
    pass, so a stop that is no longer overstaying has its assignment closed instead
    of leaving a row nothing could resolve. This job is the only queuer of Vehicle
    Suspension, so its own findings are the reconcile union.
    """
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
    """Custom Number Card: how many vehicles are overstaying in the workshop.

    Same rule as the Maintenance Overdue alert, shared via ``_overstay_stops`` so
    the card and the alert cannot disagree. Scoped to the viewer's permitted
    projects to match the other fleet number cards. ``filters`` is accepted and
    ignored (the Custom Number Card widget always passes it).
    """
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
