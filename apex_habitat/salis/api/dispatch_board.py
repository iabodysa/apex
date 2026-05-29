"""Salis Dispatch Board API (read-only glance board).

A thin presentation layer over the Salis fleet DocTypes, mirroring the Habitat
Transfer Board / Front Desk pattern: a single bounded reader per board load (no
N+1), no write/posting/status logic of its own, and no raw SQL against the data
tables. The board answers one operational question for a fleet manager: "what is
the state of my fleet right now?" across four panes:

  * vehicles grouped by status (Active / Stopped / Under Maintenance / Released);
  * today's Dispatch Trips, grouped by trip status;
  * driver availability (Active drivers split into assigned vs available, where
    "assigned" means the driver has a non-cancelled Dispatch Trip today);
  * open Transport Requests (intake not yet Scheduled / Fulfilled / Rejected /
    Cancelled).

Project scoping is enforced SERVER-SIDE and reuses the canonical Salis row-scope
helpers in :mod:`apex_habitat.salis.permissions` (``_is_unscoped`` /
``_allowed_projects``) so the board never shows a scoped supervisor any project
they could not already see in the list views:

  * Salis Vehicle, Salis Driver and Transport Request carry a direct ``project``
    Link, so they are filtered by the permitted project set;
  * Dispatch Trip has NO own ``project`` — it is scoped through its parent Route
    Plan's project, exactly as ``permissions.dispatch_trip_query`` does for the
    list view.

A scoped user with no allowed projects sees an empty board (mirroring the
``1=0`` fragment the list-view query condition would apply).

This endpoint is read-only and stays GET. It is permission-gated on
``Salis Vehicle`` / ``read`` as defence in depth on top of the Page role grant.
"""

from __future__ import annotations

import frappe
from frappe.utils import today

from apex_habitat.salis.permissions import _allowed_projects, _is_unscoped

# Canonical status ladders, kept in board order. These mirror the Select
# options on the underlying DocTypes; any value seen on a record that is not in
# the ladder is still surfaced under an "Other" bucket so the board never
# silently drops a record.
VEHICLE_STATUSES = ["Active", "Stopped", "Under Maintenance", "Released"]
TRIP_STATUSES = ["Planned", "Dispatched", "Completed", "Cancelled"]

# Transport Request statuses that are considered "closed" for intake purposes.
# Anything outside this set is an open request still awaiting routing/dispatch.
CLOSED_REQUEST_STATUSES = {"Scheduled", "Fulfilled", "Rejected", "Cancelled"}


def _permitted_projects():
    """Resolve the project scope for the current user.

    Returns a tuple ``(unscoped, projects)``:

      * ``unscoped`` is True for oversight roles that see every project, in which
        case ``projects`` is ``None`` (no project filter applied);
      * otherwise ``projects`` is the list of Project names the user holds a User
        Permission for. An empty list means the user is scoped but granted no
        project, so the board must be empty.

    This delegates to the same helpers the ``permission_query_conditions`` hooks
    use, so the board scope and the list-view scope can never diverge.
    """
    user = frappe.session.user
    if _is_unscoped(user):
        return True, None
    return False, _allowed_projects(user)


def _project_filter(unscoped, projects):
    """Build an ORM filter clause for a direct ``project`` Link column.

    Returns an empty dict for unscoped users (no restriction), or a
    ``{"project": ["in", [...]]}`` clause for scoped users.
    """
    if unscoped:
        return {}
    return {"project": ["in", projects]}


@frappe.whitelist()
def get_dispatch_board(project: str | None = None) -> dict:
    """Return the full dispatch glance board for the permitted project scope.

    Read-only. One bounded query per pane (no N+1); display titles for trips are
    resolved through bulk lookups. Permission-gated on ``Salis Vehicle`` /
    ``read``.

    Args:
        project: Optional Project docname to narrow the board to a single
            project. It is intersected with the caller's permitted scope — a
            scoped user cannot widen their view by passing a project they are not
            granted (an out-of-scope project simply yields an empty board).

    Returns:
        dict with keys:
          * ``scope``: ``{"unscoped", "projects", "project"}`` echoing the
            resolved scope (useful for the UI and for tests);
          * ``vehicles``: ``{"groups": [...], "total"}`` grouped by status;
          * ``trips_today``: ``{"groups": [...], "total", "trip_date"}`` grouped
            by Dispatch Trip status for today;
          * ``drivers``: ``{"assigned", "available", "assigned_count",
            "available_count", "active_total"}``;
          * ``transport_requests``: ``{"open": [...], "open_count"}``.
    """
    frappe.has_permission("Salis Vehicle", "read", throw=True)

    unscoped, projects = _permitted_projects()

    # Intersect an explicitly requested project with the permitted scope. A
    # scoped user must never be able to widen their view via the argument.
    if project:
        if unscoped:
            projects = [project]
            unscoped = False
        elif project in (projects or []):
            projects = [project]
        else:
            # Requested project is outside the caller's scope: empty board.
            projects = []

    # Scoped user with no permitted project => empty board (mirrors `1=0`).
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
    """A fully-formed empty board for a scoped user with no permitted project."""
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
    """Bucket ``rows`` by their status into the given ladder order.

    Statuses not present in ``ladder`` are collected under a trailing "Other"
    group so nothing is silently dropped. Empty ladder buckets are still emitted
    (with an empty ``items`` list and zero ``count``) so the UI can render a
    stable set of columns; the "Other" bucket is only emitted when non-empty.
    """
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
    """Vehicles grouped by operational status within the permitted scope."""
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
    """Today's Dispatch Trips grouped by trip status.

    Dispatch Trip has no own ``project`` field, so scoping is applied through
    the parent Route Plan exactly as ``permissions.dispatch_trip_query`` does:
    the trip's ``route_plan`` must belong to a Route Plan whose ``project`` is in
    the permitted set. Vehicle plate and driver name are resolved with bounded
    bulk reads (no per-row round trips).
    """
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

    _decorate_vehicle_driver_titles(rows)
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
    """Active drivers split into assigned vs available within scope.

    A driver is "assigned" when they have at least one non-cancelled Dispatch
    Trip dated today (the operational dispatch sense); every other Active driver
    is "available". ``current_vehicle`` is surfaced on each row so the board can
    show the bound vehicle without an extra round trip. Only ``Active`` drivers
    are considered for the availability split (Stopped / On Leave / Released
    drivers are out of the dispatchable pool).
    """
    driver_filters = _project_filter(unscoped, projects)
    driver_filters["status"] = "Active"

    drivers = frappe.get_all(
        "Salis Driver",
        filters=driver_filters,
        fields=["name", "full_name", "status", "project", "current_vehicle", "phone"],
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

    # Drivers with a non-cancelled trip today are "assigned". Bounded single
    # query over today's trips for exactly this driver set (no N+1).
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
                "phone": d.phone,
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
    """Open Transport Requests (intake not yet closed) within scope.

    "Open" = status NOT in {Scheduled, Fulfilled, Rejected, Cancelled}. Only
    submitted or draft intake is shown (cancelled documents are excluded both by
    status and by the ``docstatus < 2`` guard).
    """
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


def _decorate_vehicle_driver_titles(rows) -> None:
    """Attach ``vehicle_plate`` and ``driver_name`` to trip rows in bulk.

    Resolves the display titles for every distinct vehicle and driver referenced
    by ``rows`` in two bounded queries, then maps them back onto each row. Falls
    back to the docname when a title is missing.
    """
    vehicle_names = list({r.vehicle for r in rows if r.get("vehicle")})
    driver_names = list({r.driver for r in rows if r.get("driver")})

    plate_by_vehicle: dict = {}
    if vehicle_names:
        for v in frappe.get_all(
            "Salis Vehicle",
            filters={"name": ["in", vehicle_names]},
            fields=["name", "plate_number"],
        ):
            plate_by_vehicle[v.name] = v.get("plate_number")

    name_by_driver: dict = {}
    if driver_names:
        for d in frappe.get_all(
            "Salis Driver",
            filters={"name": ["in", driver_names]},
            fields=["name", "full_name"],
        ):
            name_by_driver[d.name] = d.get("full_name")

    for r in rows:
        r["vehicle_plate"] = plate_by_vehicle.get(r.get("vehicle")) or r.get("vehicle")
        r["driver_name"] = name_by_driver.get(r.get("driver")) or r.get("driver")
