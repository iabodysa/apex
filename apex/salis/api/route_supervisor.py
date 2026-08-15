# Copyright (c) 2026, afmcoltd
"""Masar supervisor API for recurring assignments and actual trips.

No live driver position is served. ``Dispatch Trip.driver_lat`` / ``driver_lng`` /
``driver_position_updated_at`` still exist as columns, but their only writer —
``driver_portal.push_driver_position`` — was removed with the legacy portal, and
``apex/www/test_portal_shell_contract.py`` now asserts it stays removed. They are Float
columns, which Frappe emits NOT NULL DEFAULT 0, so a trip that has never reported a fix
reads back 0.0 and any ``is not None`` test on them answers True forever. Reporting a
position nobody wrote is worse than reporting none: the supervisor map states the driver
is at 0,0 off the coast of Africa. The keys are therefore gone from the response, and
the client renders its own "position unavailable" state for a row that carries none."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, today

from apex.salis.utils.road_route import is_cached, road_path

PORTAL_ROLES = (
    "Fleet Supervisor",
    "Fleet Project Manager",
    "Fleet Manager",
    "System Manager",
)

PLAN_PAGE_LENGTH = 50
ROUTER_CALLS_PER_REQUEST = 3


def _require_portal_role():
    user = frappe.session.user
    if user == "Administrator":
        return
    if not set(frappe.get_roles(user)).intersection(PORTAL_ROLES):
        frappe.throw(_("This portal is for route supervisors."), frappe.PermissionError)


def _validate_page(start, page_length):
    start = cint(start)
    page_length = cint(page_length)
    if start < 0:
        frappe.throw(_("Page start cannot be negative."), frappe.ValidationError)
    if not 1 <= page_length <= PLAN_PAGE_LENGTH:
        frappe.throw(
            _("Page length must be between 1 and {0}.").format(PLAN_PAGE_LENGTH),
            frappe.ValidationError,
        )
    return start, page_length


def _validate_position_page(start, page_length):
    return _validate_page(start, page_length)


def _label_map(doctype, label_field, names):
    names = sorted({name for name in names if name})
    if not names:
        return {}
    return {
        row.name: row.get(label_field) or row.name
        for row in frappe.get_all(
            doctype,
            filters={"name": ["in", names]},
            fields=["name", label_field],
        )
    }


def _trip_stops(trip_names):
    stops = {}
    if not trip_names:
        return stops
    for row in frappe.get_all(
        "Route Stop",
        filters={
            "parent": ["in", trip_names],
            "parenttype": "Dispatch Trip",
        },
        fields=["parent", "stop_key", "stop_name", "latitude", "longitude", "idx"],
        order_by="parent asc, idx asc",
    ):
        stops.setdefault(row.parent, []).append(row)
    return stops


def _map_stop(row):
    return {
        "stop_key": row.get("stop_key"),
        "stop_name": row.get("stop_name"),
        "lat": row.get("latitude"),
        "lng": row.get("longitude"),
    }


@frappe.whitelist()
def get_active_driver_positions(start=0, page_length=PLAN_PAGE_LENGTH):
    """Return today's planned trips and every still-dispatched trip."""
    _require_portal_role()
    start, page_length = _validate_page(start, page_length)
    rows = frappe.get_list(
        "Dispatch Trip",
        filters={"status": ["in", ["Planned", "Dispatched"]]},
        or_filters=[
            ["Dispatch Trip", "trip_date", "=", today()],
            ["Dispatch Trip", "status", "=", "Dispatched"],
        ],
        fields=[
            "name",
            "trip_title",
            "route_assignment",
            "project",
            "project.project_name as project_label",
            "status",
            "driver",
            "vehicle",
            "planned_start",
        ],
        order_by="planned_start asc, name asc",
        limit_start=start,
        limit_page_length=page_length + 1,
    )
    has_more = len(rows) > page_length
    trips = rows[:page_length]
    stops_by_trip = _trip_stops([row.name for row in trips])
    driver_labels = _label_map(
        "Salis Driver", "full_name", [row.driver for row in trips]
    )
    vehicle_labels = _label_map(
        "Salis Vehicle", "plate_number", [row.vehicle for row in trips]
    )

    positions = []
    router_budget = ROUTER_CALLS_PER_REQUEST
    for trip in trips:
        stops = [
            _map_stop(row)
            for row in stops_by_trip.get(trip.name, [])
            if row.latitude is not None and row.longitude is not None
        ]
        coordinates = [(row["lat"], row["lng"]) for row in stops]
        path = []
        if coordinates:
            warm = is_cached(coordinates)
            path = road_path(
                coordinates, cached_only=not warm and router_budget <= 0
            )
            if not warm:
                router_budget -= 1
        positions.append(
            {
                "dispatch_trip": trip.name,
                "route_assignment": trip.route_assignment,
                "route_name": trip.trip_title or trip.name,
                "stops": stops,
                "path": path,
                "project": trip.project,
                "project_label": trip.project_label or trip.project,
                "status": trip.status,
                "driver": trip.driver,
                "driver_name": driver_labels.get(trip.driver, trip.driver),
                "vehicle": trip.vehicle,
                "plate": vehicle_labels.get(trip.vehicle, trip.vehicle),
            }
        )

    return {
        "positions": positions,
        "start": start,
        "page_length": page_length,
        "returned": len(positions),
        "has_more": has_more,
    }

