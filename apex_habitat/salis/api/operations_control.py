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

from apex_habitat.salis.api.dispatch_board import _permitted_projects

VEHICLE_STATUSES = ["Active", "Stopped", "Under Maintenance", "Released"]


def _empty(offices=None, projects=None, unscoped=False):
    return {
        "vehicles": [],
        "summary": {"total": 0, "by_status": {s: 0 for s in VEHICLE_STATUSES}, "open_incidents": 0},
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
    frappe.has_permission("Salis Vehicle", "read", throw=True)
    unscoped, projects = _permitted_projects()

    offices = [o.name for o in frappe.get_all("Rental Office", fields=["name"], order_by="name asc")]
    proj_opts = (
        [p.name for p in frappe.get_all("Project", fields=["name"], order_by="name asc", limit_page_length=0)]
        if unscoped
        else list(projects or [])
    )
    if not unscoped and not projects:
        return _empty(offices, proj_opts, unscoped)

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

    summary = {"total": len(vehicles), "by_status": {s: 0 for s in VEHICLE_STATUSES}, "open_incidents": 0}
    for v in vehicles:
        v["current_driver_name"] = names.get(v.get("current_driver"))
        v["open_incidents"] = inc.get(v.name, 0)
        summary["open_incidents"] += v["open_incidents"]
        if v.status in summary["by_status"]:
            summary["by_status"][v.status] += 1

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
