# Copyright (c) 2026, AFMCO and contributors
"""Fleet Control board API (read-only fleet view with details, for the
``operations-control`` desk page).

Mirrors the Salis Dispatch Board reader pattern: bounded, N+1-free readers, no
raw SQL, no writes, permission-gated on ``Salis Vehicle`` / ``read`` on top of
the Page role grant, and project-scoped server-side through the SAME
``_permitted_projects`` resolver the dispatch board and the list-view
``permission_query_conditions`` use, so the board never shows a scoped
supervisor a project they could not already see.

The board answers "what is every vehicle's state, driver and open-incident load
right now?" and powers a card/table view and a per-vehicle detail drawer.
"""

from __future__ import annotations

import frappe
from frappe import _
from apex.salis.api.dispatch_board import VEHICLE_STATUSES
from apex.salis.api.fleet_reader import driver_names, scope_filter, scoped_vehicles
from apex.salis.utils import close_open_stop, lock_vehicle, reassign_vehicle_driver

COMPLIANCE_AT_RISK = ("Expiring Soon", "Expired")

COMPLIANCE_FILTERS = ("Compliant", "Expiring Soon", "Expired")


def _empty_summary(stopped_over_days):
    return {
        "total": 0,
        "by_status": {s: 0 for s in VEHICLE_STATUSES},
        "open_incidents": 0,
        "compliance_at_risk": 0,
        "stopped_over_n": 0,
        "stopped_over_days": stopped_over_days,
    }


def _empty(offices=None, projects=None, unscoped=False, stopped_over_days=14):
    return {
        "vehicles": [],
        "summary": _empty_summary(stopped_over_days),
        "offices": offices or [],
        "projects": projects or [],
        "statuses": VEHICLE_STATUSES,
        "unscoped": unscoped,
    }


@frappe.whitelist()
def get_fleet(status=None, rental_office=None, project=None, search=None, compliance=None):
    """Return the filtered fleet with driver names and open-incident counts.

    All filters are optional. Project scope is enforced server-side: a scoped
    user with no permitted project gets an empty board. ``compliance`` narrows to
    one of Compliant / Expiring Soon / Expired (the vehicle's compliance_status).
    """
    from apex.salis.tasks import _settings_int

    frappe.has_permission("Salis Vehicle", "read", throw=True)
    unscoped, projects, base_filters = scope_filter()
    stopped_over_days = _settings_int("workshop_overstay_days", 14)

    offices = [o.name for o in frappe.get_all("Rental Office", fields=["name"], order_by="name asc")]
    proj_opts = (
        [p.name for p in frappe.get_all("Project", fields=["name"], order_by="name asc", limit_page_length=0)]
        if unscoped
        else list(projects or [])
    )
    if base_filters is None:
        return _empty(offices, proj_opts, unscoped, stopped_over_days)

    extra = {}
    if status in VEHICLE_STATUSES:
        extra["status"] = status
    if rental_office:
        extra["rental_office"] = rental_office
    if project and (unscoped or project in (projects or [])):
        extra["project"] = project
    if compliance in COMPLIANCE_FILTERS:
        extra["compliance_status"] = compliance

    or_filters = None
    if search:
        like = ["like", f"%{search}%"]
        or_filters = {"plate_number": like, "vehicle_category": like, "current_driver": like}

    vehicles = scoped_vehicles(
        fields=[
            "name", "plate_number", "vehicle_category", "status", "ownership",
            "rental_office", "project", "current_driver", "odometer", "planned_fuel_grade",
            "compliance_status", "next_expiry_date",
        ],
        base_filters=base_filters,
        extra_filters=extra,
        or_filters=or_filters,
    )

    names = driver_names(vehicles)

    plates = [v.name for v in vehicles]
    inc = {}
    if plates:
        for r in frappe.get_all(
            "Vehicle Incident",
            filters={"vehicle": ["in", plates], "status": "Open", "docstatus": ["<", 2]},
            fields=["vehicle", "count(name) as c"],
            group_by="vehicle",
        ):
            inc[r.vehicle] = r.c

    summary = {
        "total": len(vehicles),
        "by_status": {s: 0 for s in VEHICLE_STATUSES},
        "open_incidents": 0,
        "compliance_at_risk": 0,
        "stopped_over_days": stopped_over_days,
    }
    for v in vehicles:
        v["current_driver_name"] = names.get(v.get("current_driver"))
        v["open_incidents"] = inc.get(v.name, 0)
        summary["open_incidents"] += v["open_incidents"]
        if v.status in summary["by_status"]:
            summary["by_status"][v.status] += 1
        if v.get("compliance_status") in COMPLIANCE_AT_RISK:
            summary["compliance_at_risk"] += 1

    from apex.salis.tasks import _overstay_stops

    on_board = {v.name for v in vehicles}
    summary["stopped_over_n"] = len({r.vehicle for r in _overstay_stops()} & on_board)

    return {
        "vehicles": vehicles,
        "summary": summary,
        "offices": offices,
        "projects": proj_opts,
        "statuses": VEHICLE_STATUSES,
        "unscoped": unscoped,
    }


@frappe.whitelist()
def get_vehicle_detail(vehicle):
    """Return one vehicle's detail: master fields, recent incidents and recent
    custody assignments. Permission- and scope-gated like the board."""
    frappe.has_permission("Salis Vehicle", "read", doc=vehicle, throw=True)
    v = frappe.db.get_value(
        "Salis Vehicle",
        vehicle,
        ["name", "plate_number", "vehicle_category", "status", "ownership", "rental_office",
         "project", "current_driver", "odometer", "planned_fuel_grade", "compliance_status", "next_expiry_date"],
        as_dict=True,
    )
    if not v:
        frappe.throw(frappe._("Vehicle not found."))
    if v.current_driver:
        v["current_driver_name"] = frappe.db.get_value("Salis Driver", v.current_driver, "full_name")

    incidents = frappe.get_all(
        "Vehicle Incident",
        filters={"vehicle": vehicle},
        fields=["name", "incident_type", "incident_date", "status", "location"],
        order_by="incident_date desc",
        limit=10,
    )
    assignments = frappe.get_all(
        "Vehicle Assignment",
        filters={"vehicle": vehicle},
        fields=["name", "driver", "start_date", "end_date", "status"],
        order_by="start_date desc",
        limit=10,
    )
    return {"vehicle": v, "incidents": incidents, "assignments": assignments}


TIMELINE_PER_SOURCE = 20
TIMELINE_LIMIT = 40


@frappe.whitelist()
def get_vehicle_timeline(vehicle):
    """Return one vehicle's consolidated operational history as a single date-sorted feed.

    Unions the event sources into one timeline — Vehicle Incident, Vehicle Suspension,
    Vehicle Assignment and the drained Fleet Supervisor assignment queue — so the drawer shows the whole
    operational story of a vehicle in one place instead of three disconnected lists.
    Permission- and scope-gated identically to ``get_vehicle_detail``: read access to
    the vehicle is the single chokepoint (once you may read the vehicle you may read its
    own history). Bounded per source and overall, N+1-free (no per-row queries). Each
    row is a normalised ``{kind, date, ...}`` event; ``date`` is ISO so the client sorts
    and renders without reparsing per source.

    The existence probe is name-filtered, not positional: the positional
    ``frappe.db.exists(dt, dn)`` answers the value back unqueried when it equals the
    DocType (database.py:1259), and Administrator short-circuits the permission check
    above it (permissions.py:107) — so the literal "Salis Vehicle" reached here,
    cleared this gate and returned an empty feed as a success.
    """
    frappe.has_permission("Salis Vehicle", "read", doc=vehicle, throw=True)
    if not frappe.db.exists("Salis Vehicle", {"name": vehicle}):
        frappe.throw(_("Vehicle not found."))

    events = []

    for r in frappe.get_all(
        "Vehicle Incident",
        filters={"vehicle": vehicle},
        fields=["name", "incident_type", "incident_date", "status", "location"],
        order_by="incident_date desc",
        limit=TIMELINE_PER_SOURCE,
    ):
        events.append({
            "kind": "incident",
            "date": str(r.incident_date) if r.incident_date else None,
            "name": r.name,
            "incident_type": r.incident_type,
            "status": r.status,
            "location": r.location,
        })

    for r in frappe.get_all(
        "Vehicle Suspension",
        filters={"vehicle": vehicle, "docstatus": ["<", 2]},
        fields=["name", "stop_reason", "stop_date", "return_date", "related_driver"],
        order_by="stop_date desc",
        limit=TIMELINE_PER_SOURCE,
    ):
        events.append({
            "kind": "stop",
            "date": str(r.stop_date) if r.stop_date else None,
            "name": r.name,
            "stop_reason": r.stop_reason,
            "return_date": str(r.return_date) if r.return_date else None,
            "driver": r.related_driver,
        })

    for r in frappe.get_all(
        "Vehicle Assignment",
        filters={"vehicle": vehicle},
        fields=["name", "driver", "start_date", "end_date", "status"],
        order_by="start_date desc",
        limit=TIMELINE_PER_SOURCE,
    ):
        events.append({
            "kind": "assignment",
            "date": str(r.start_date) if r.start_date else None,
            "name": r.name,
            "driver": r.driver,
            "end_date": str(r.end_date) if r.end_date else None,
            "status": r.status,
        })

    from apex.salis.api.assignment_queue import queue_events_for_vehicle

    for r in queue_events_for_vehicle(vehicle, ("Closed",), TIMELINE_PER_SOURCE):
        events.append({
            "kind": "alert",
            "date": str(r.closed_on) if r.closed_on else None,
            "name": r.name,
            "alert_type": r.alert_type,
            "severity": r.severity,
            "message": r.message,
        })

    events.sort(key=lambda e: e["date"] or "", reverse=True)
    return {"vehicle": vehicle, "events": events[:TIMELINE_LIMIT]}


@frappe.whitelist(methods=["POST"])
def release_vehicle(vehicle, return_date=None):
    """Release a Stopped vehicle back to service from the Fleet Control drawer.

    Closes the vehicle's open (submitted) Vehicle Suspension through the NATIVE
    submittable lifecycle: the release fields are stamped on the stop and the
    document is then cancelled, so ``VehicleStop.on_cancel`` is what restores the
    vehicle to its ``previous_status`` (controllers are not bypassed — we never
    poke ``Salis Vehicle.status`` directly). Permission is re-checked on the
    vehicle ("write") on top of the Page role grant.

    ``return_date`` (the workshop-exit date) defaults to today; ``released_on`` is
    stamped to today and ``released_by`` to the acting user. Returns the closed
    stop name. Throws when the vehicle has no open stop (e.g. it is not Stopped,
    or a concurrent release already closed it).
    """
    frappe.has_permission("Salis Vehicle", "write", doc=vehicle, throw=True)
    lock_vehicle(vehicle)

    stop = frappe.db.get_value(
        "Vehicle Suspension",
        {"vehicle": vehicle, "docstatus": 1},
        "name",
        order_by="creation desc",
    )
    if not stop:
        frappe.throw(_("This vehicle has no open stop to release."))

    close_open_stop(stop, return_date)
    return {"ok": True, "stop": stop}


@frappe.whitelist(methods=["POST"])
def reassign_driver(vehicle, driver, start_date=None):
    """Reassign a vehicle's driver from the Fleet Control drawer.

    Ends the vehicle's current Active Vehicle Assignment and starts a new one
    through the NATIVE submit lifecycle: VehicleAssignment.on_submit is what
    stamps Salis Vehicle.current_driver and the driver's current_vehicle, and its
    validate/on_submit overlap guards still run (controllers are not bypassed). We
    never poke the driver links directly. Permission is re-checked on the vehicle
    ("write") on top of the Page role grant, and on the incoming driver ("write")
    since the new assignment puts the company vehicle in their custody.

    ``driver`` is the Salis Driver name (the detail drawer carries the name, not
    the external driver_id). ``start_date`` defaults to today and dates the close
    of the old assignment and the start of the new one. Returns the new
    assignment name.
    """
    if not driver:
        frappe.throw(_("Driver is required."))
    frappe.has_permission("Salis Vehicle", "write", doc=vehicle, throw=True)
    if not frappe.db.exists("Salis Driver", {"name": driver}):
        frappe.throw(_("Driver {0} not found.").format(driver))
    frappe.has_permission("Salis Driver", "write", doc=driver, throw=True)

    assignment = reassign_vehicle_driver(vehicle, driver, start_date, reject_same_driver=True)
    return {"ok": True, "assignment": assignment}
