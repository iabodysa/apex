"""Fleet Control board API (read-only fleet view with details, for the
``operations-control`` desk page).

Mirrors the Salis Dispatch Board reader pattern: bounded, N+1-free readers, no
raw SQL, no writes, permission-gated on ``Salis Vehicle`` / ``read`` on top of
the Page role grant, and project-scoped server-side through the SAME
``_permitted_projects`` resolver the dispatch board and the list-view
``permission_query_conditions`` use, so the board never shows a scoped
supervisor a project they could not already see.

The board answers "what is every vehicle's state, driver and open-incident load
right now?" and powers a card/table view, a per-vehicle detail drawer, and a
client-side CSV export of the current view.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, today

from apex_habitat.salis.api.dispatch_board import _permitted_projects
from apex_habitat.salis.utils import lock_vehicle

VEHICLE_STATUSES = ["Active", "Stopped", "Under Maintenance", "Released"]

# Compliance states that count a vehicle as "at risk" — the same two the card flags.
COMPLIANCE_AT_RISK = ("Expiring Soon", "Expired")


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
        # Lets the client tell a scoped-but-no-project gap apart from an empty filter.
        "unscoped": unscoped,
    }


@frappe.whitelist()
def get_fleet(status=None, rental_office=None, project=None, search=None):
    """Return the filtered fleet with driver names and open-incident counts.

    All filters are optional. Project scope is enforced server-side: a scoped
    user with no permitted project gets an empty board.
    """
    from apex_habitat.salis.tasks import _settings_int

    frappe.has_permission("Salis Vehicle", "read", throw=True)
    unscoped, projects = _permitted_projects()
    stopped_over_days = _settings_int("workshop_overstay_days", 14)

    offices = [o.name for o in frappe.get_all("Rental Office", fields=["name"], order_by="name asc")]
    proj_opts = (
        [p.name for p in frappe.get_all("Project", fields=["name"], order_by="name asc", limit_page_length=0)]
        if unscoped
        else list(projects or [])
    )
    if not unscoped and not projects:
        return _empty(offices, proj_opts, unscoped, stopped_over_days)

    filters = {}
    if not unscoped:
        filters["project"] = ["in", projects]
    if status in VEHICLE_STATUSES:
        filters["status"] = status
    if rental_office:
        filters["rental_office"] = rental_office
    if project and (unscoped or project in (projects or [])):
        filters["project"] = project

    or_filters = None
    if search:
        like = ["like", f"%{search}%"]
        or_filters = {"plate_number": like, "vehicle_category": like, "current_driver": like}

    vehicles = frappe.get_all(
        "Salis Vehicle",
        filters=filters,
        or_filters=or_filters,
        fields=[
            "name", "plate_number", "vehicle_category", "status", "ownership",
            "rental_office", "project", "current_driver", "odometer", "planned_fuel_grade",
            "compliance_status", "next_expiry_date",
        ],
        order_by="plate_number asc",
        limit_page_length=0,
    )

    driver_ids = list({v.current_driver for v in vehicles if v.get("current_driver")})
    names = {}
    if driver_ids:
        names = {
            d.name: d.full_name
            for d in frappe.get_all("Salis Driver", filters={"name": ["in", driver_ids]}, fields=["name", "full_name"])
        }

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

    # "Stopped > N days": reuse the workshop-overstay rule (single source of truth in
    # tasks._overstay_stops) so the chip can never disagree with the alert / number card.
    # Intersect with the already-scoped board so the count respects project scope.
    from apex_habitat.salis.tasks import _overstay_stops

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


@frappe.whitelist(methods=["POST"])
def release_vehicle(vehicle, return_date=None):
    """Release a Stopped vehicle back to service from the Fleet Control drawer.

    Closes the vehicle's open (submitted) Vehicle Stop through the NATIVE
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
        "Vehicle Stop",
        {"vehicle": vehicle, "docstatus": 1},
        "name",
        order_by="creation desc",
    )
    if not stop:
        frappe.throw(_("This vehicle has no open stop to release."))

    on = getdate(today())
    ret = getdate(return_date) if return_date else on
    # Audit stamps on the submitted stop; not allow_on_submit, so set them directly
    # before the cancel transition runs the native reversal (on_cancel).
    frappe.db.set_value(
        "Vehicle Stop",
        stop,
        {"return_date": ret, "released_on": on, "released_by": frappe.session.user},
    )
    # on_cancel restores the vehicle's previous_status (controllers not bypassed).
    frappe.get_doc("Vehicle Stop", stop).cancel()
    return {"ok": True, "stop": stop}
