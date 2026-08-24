# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import today

from apex.salis.api.enrich import vehicle_driver_titles
from apex.salis.permissions import allowed_projects, _is_unscoped

VEHICLE_STATUSES = ["Active", "Stopped", "Under Maintenance", "Released"]
TRIP_STATUSES = ["Planned", "Dispatched", "Completed", "Cancelled"]

CLOSED_REQUEST_STATUSES = {"Scheduled", "Fulfilled", "Rejected", "Cancelled"}


def _permitted_projects():
    user = frappe.session.user
    if _is_unscoped(user):
        return True, None
    return False, allowed_projects(user)


def _project_filter(unscoped, projects):
    if unscoped:
        return {}
    return {"project": ["in", projects]}


@frappe.whitelist()
def get_dispatch_board(project: str | None = None) -> dict:
    frappe.has_permission("Salis Vehicle", "read", throw=True)
    frappe.has_permission("Dispatch Trip", "read", throw=True)

    unscoped, projects = _permitted_projects()

    if project:
        if unscoped:
            projects = [project]
            unscoped = False
        elif project in (projects or []):
            projects = [project]
        else:
            projects = []

    if not unscoped and not projects:
        return _empty_board(unscoped, projects, project)

    return {
        "scope": {"unscoped": unscoped, "projects": projects, "project": project},
        "vehicles": _vehicles_pane(unscoped, projects),
        "trips_today": _trips_today_pane(unscoped, projects),
        "drivers": _drivers_pane(unscoped, projects),
        "transport_requests": _transport_requests_pane(unscoped, projects),
    }


def _empty_board(unscoped, projects, project) -> dict:
    return {
        "scope": {"unscoped": unscoped, "projects": projects, "project": project},
        "vehicles": {"groups": [], "total": 0},
        "trips_today": {"groups": [], "total": 0, "trip_date": today()},
        "drivers": {
            "assigned": [],
            "available": [],
            "assigned_count": 0,
            "available_count": 0,
            "active_total": 0,
        },
        "transport_requests": {"open": [], "open_count": 0},
    }


def _group_by_status(rows, ladder, status_key="status"):
    buckets: dict[str, list] = {status: [] for status in ladder}
    other: list = []
    for row in rows:
        status = row.get(status_key)
        if status in buckets:
            buckets[status].append(row)
        else:
            other.append(row)

    groups = [
        {"status": status, "count": len(items), "items": items}
        for status, items in ((s, buckets[s]) for s in ladder)
    ]
    if other:
        groups.append({"status": "Other", "count": len(other), "items": other})
    return groups


def _vehicles_pane(unscoped, projects) -> dict:
    rows = frappe.get_all(
        "Salis Vehicle",
        filters=_project_filter(unscoped, projects),
        fields=[
            "name",
            "plate_number",
            "vehicle_category",
            "status",
            "ownership",
            "project",
            "current_driver",
            "compliance_status",
            "odometer",
        ],
        order_by="plate_number asc",
        limit_page_length=0,
    )
    return {
        "groups": _group_by_status(rows, VEHICLE_STATUSES),
        "total": len(rows),
    }


def _trips_today_pane(unscoped, projects) -> dict:
    trip_date = today()
    filters: dict = {"trip_date": trip_date}

    if not unscoped:
        permitted_route_plans = frappe.get_all(
            "Route Plan",
            filters={"project": ["in", projects]},
            pluck="name",
        )
        if not permitted_route_plans:
            return {"groups": [], "total": 0, "trip_date": trip_date}
        filters["route_plan"] = ["in", permitted_route_plans]

    rows = frappe.get_all(
        "Dispatch Trip",
        filters=filters,
        fields=[
            "name",
            "route_plan",
            "transport_request",
            "vehicle",
            "driver",
            "trip_date",
            "depart_time",
            "return_time",
            "status",
        ],
        order_by="depart_time asc, name asc",
        limit_page_length=0,
    )

    vehicle_driver_titles(rows)
    for r in rows:
        r["depart_time"] = str(r["depart_time"]) if r.get("depart_time") else None
        r["return_time"] = str(r["return_time"]) if r.get("return_time") else None
        r["trip_date"] = str(r["trip_date"]) if r.get("trip_date") else None

    return {
        "groups": _group_by_status(rows, TRIP_STATUSES),
        "total": len(rows),
        "trip_date": trip_date,
    }


def _drivers_pane(unscoped, projects) -> dict:
    driver_filters = _project_filter(unscoped, projects)
    driver_filters["status"] = "Active"
    show_pii = 1 in frappe.get_meta("Salis Driver").get_permlevel_access("read")

    driver_fields = ["name", "full_name", "status", "project", "current_vehicle"]
    if show_pii:
        driver_fields.append("phone")

    drivers = frappe.get_all(
        "Salis Driver",
        filters=driver_filters,
        fields=driver_fields,
        order_by="full_name asc",
        limit_page_length=0,
    )
    if not drivers:
        return {
            "assigned": [],
            "available": [],
            "assigned_count": 0,
            "available_count": 0,
            "active_total": 0,
        }

    driver_names = [d.name for d in drivers]

    assigned_today = set(
        frappe.get_all(
            "Dispatch Trip",
            filters={
                "trip_date": today(),
                "driver": ["in", driver_names],
                "status": ["!=", "Cancelled"],
            },
            pluck="driver",
            limit_page_length=0,
        )
    )

    assigned, available = [], []
    for d in drivers:
        bucket = assigned if d.name in assigned_today else available
        bucket.append(
            {
                "name": d.name,
                "full_name": d.full_name or d.name,
                "project": d.project,
                "current_vehicle": d.current_vehicle,
                "phone": (d.get("phone") or "") if show_pii else "",
            }
        )

    return {
        "assigned": assigned,
        "available": available,
        "assigned_count": len(assigned),
        "available_count": len(available),
        "active_total": len(drivers),
    }


def _transport_requests_pane(unscoped, projects) -> dict:
    filters = _project_filter(unscoped, projects)
    filters["status"] = ["not in", list(CLOSED_REQUEST_STATUSES)]
    filters["docstatus"] = ["<", 2]

    rows = frappe.get_all(
        "Transport Request",
        filters=filters,
        fields=[
            "name",
            "service_line",
            "request_type",
            "project",
            "status",
            "passenger_count",
            "worker_count",
            "from_location",
            "to_location",
            "destination",
            "pickup_datetime",
            "is_cross_region",
        ],
        order_by="pickup_datetime asc, modified desc",
        limit_page_length=0,
    )
    for r in rows:
        r["pickup_datetime"] = (
            str(r["pickup_datetime"]) if r.get("pickup_datetime") else None
        )

    return {"open": rows, "open_count": len(rows)}
