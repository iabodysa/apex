# Copyright (c) 2026, afmcoltd
"""Masar route, trip and stop reading — the shared trip domain.

One home for the question "what does a worker trip look like": the date window a
trip is boardable in, the Workers-line trips a driver is running today, the
ordered Route Stops with their Habitat pickups, the registered manifest, which
stop belongs to which worker, and the ride ETA.

It is shared on purpose. The DRIVER route endpoints
(``masar.get_my_worker_route_today`` / ``_summary``) and the WORKER transport
endpoints (``masar.get_worker_transport``, ``masar.get_worker_boarding_pass``,
``masar.confirm_boarding``) read the same trips from opposite ends, and every one
of these readers had two callers before it lived here. Changing what a stop
carries, or when a night run stops being boardable, is one edit in this file.

Reads only: nothing here writes, commits or posts GL. Identity is resolved by the
caller — every function takes an already-resolved driver or employee id and none
of them widens that scope.
"""

import frappe

from apex.salis.api import boarding_window

WORKER_SERVICE_LINES = ("Site Transport", "Inter-City Relocation")

_FINISHED_TRIP_STATUSES = boarding_window.FINISHED_TRIP_STATUSES

def _fmt_time(value):
    """Render a Time field as a clean zero-padded ``HH:MM:SS`` string (or None).

    Frappe stores Time as a ``datetime.timedelta``; ``cstr`` on it yields an
    unpadded value with stray microseconds (e.g. ``6:30:00`` /
    ``2:05:46.198544``). ``format_time`` normalises it to ``06:30:00`` for a clean
    JSON payload.

    ``frappe.utils.format_time`` (frappe/utils/data.py:583) treats a blank value
    and a malformed one the same way a display label would — "" for one, a raised
    exception for the other — neither of which a JSON API can return; this
    coalesces blank to ``None`` and a parse failure to the raw ``cstr`` value
    instead of propagating the exception to the caller."""
    if value in (None, ""):
        return None
    try:
        return frappe.utils.format_time(value)
    except Exception:
        return frappe.utils.cstr(value)

def _trip_date_window():
    """The trip_date filter window for "boardable now" — today AND yesterday.

    A night shift that departs before midnight runs past it: at 00:05 the trip's
    ``trip_date`` is still yesterday, so a ``trip_date = today()`` filter drops it
    at the exact moment the worker needs to board. Including yesterday keeps that
    in-progress night trip reachable. The caller drops a YESTERDAY trip that has
    already finished (see ``_drop_finished_yesterday``), so today's completed trips
    stay visible while only an in-motion night run carries over — no double-count."""
    return ["in", [frappe.utils.add_days(frappe.utils.today(), -1), frappe.utils.today()]]

def _drop_finished_yesterday(trips):
    """Drop carried-over YESTERDAY trips that are already finished.

    The yesterday half of ``_trip_date_window`` exists only to keep a night run
    still in motion reachable past midnight; a yesterday trip that has already
    Completed/Cancelled is done and must not resurface. Today's trips pass through
    untouched in every status (the driver's route view shows today's completed
    runs). Keyed on ``trip_date``, so a row missing it is kept defensively."""
    yesterday = frappe.utils.add_days(frappe.utils.today(), -1)
    return [
        t
        for t in trips
        if not (
            frappe.utils.cstr(t.get("trip_date")) == yesterday
            and t.get("status") in _FINISHED_TRIP_STATUSES
        )
    ]

def _today_worker_trips(driver):
    """Today's (and an in-progress night shift's) Dispatch Trips for ``driver``
    whose linked Transport Request is on the Workers service line. Returns a list
    of trip dicts with the route_plan and transport_request resolved, ordered by
    departure time. A trip that left before midnight is still boardable after it,
    so the date window spans yesterday+today (see ``_trip_date_window``); a
    yesterday trip that has already finished is dropped (``_drop_finished_yesterday``)."""
    trips = frappe.get_all(
        "Dispatch Trip",
        filters={
            "driver": driver,
            "trip_date": _trip_date_window(),
            "status": "Dispatched",
            "docstatus": ["<", 2],
        },
        fields=[
            "name",
            "trip_title",
            "route_assignment",
            "route_template",
            "route_plan",
            "project",
            "transport_request",
            "vehicle",
            "trip_date",
            "depart_time",
            "return_time",
            "status",
        ],
        order_by="depart_time asc",
    )
    trips = _drop_finished_yesterday(trips)
    if not trips:
        return []
    trip_names = [t["name"] for t in trips]
    requests_by_trip = {t["name"]: [] for t in trips}
    for row in frappe.get_all(
        "Dispatch Trip Assigned Request",
        filters={"parent": ["in", trip_names], "parenttype": "Dispatch Trip"},
        fields=["parent", "transport_request"],
        order_by="parent asc, idx asc",
    ):
        if row.get("transport_request"):
            requests_by_trip[row["parent"]].append(row["transport_request"])

    rp_ids = {
        t["route_plan"]
        for t in trips
        if not t.get("transport_request") and t.get("route_plan")
    }
    if rp_ids:
        rp_tr = {
            r["name"]: r["transport_request"]
            for r in frappe.get_all(
                "Route Plan",
                filters={"name": ["in", list(rp_ids)]},
                fields=["name", "transport_request"],
            )
        }
        for t in trips:
            if not t.get("transport_request") and t.get("route_plan"):
                t["transport_request"] = rp_tr.get(t["route_plan"])

    for trip in trips:
        requests_by_trip[trip["name"]] = list(
            dict.fromkeys(
                request
                for request in [
                    trip.get("transport_request"),
                    *requests_by_trip[trip["name"]],
                ]
                if request
            )
        )

    tr_ids = {
        request for requests in requests_by_trip.values() for request in requests
    }
    service_lines = (
        {
            r["name"]: r["service_line"]
            for r in frappe.get_all(
                "Transport Request",
                filters={"name": ["in", list(tr_ids)]},
                fields=["name", "service_line"],
            )
        }
        if tr_ids
        else {}
    )
    result = []
    for trip in trips:
        requests = requests_by_trip[trip["name"]]
        if any(service_lines.get(request) in WORKER_SERVICE_LINES for request in requests):
            trip["transport_requests"] = requests
            result.append(trip)
    return result

def _registered_workers(transport_request):
    """The registered worker manifest for a Transport Request: each row's Employee
    plus the human-readable pickup point recorded on the request."""
    if not transport_request:
        return []
    rows = frappe.get_all(
        "Transport Request Worker",
        filters={"parent": transport_request, "parenttype": "Transport Request"},
        fields=["employee", "pickup_point", "notes"],
        order_by="idx asc",
    )
    emp_ids = {r["employee"] for r in rows if r.get("employee")}
    emp_names = (
        {
            e["name"]: e["employee_name"]
            for e in frappe.get_all(
                "Employee", filters={"name": ["in", list(emp_ids)]}, fields=["name", "employee_name"]
            )
        }
        if emp_ids
        else {}
    )
    workers = []
    for r in rows:
        workers.append(
            {
                "employee": r.get("employee"),
                "employee_name": (emp_names.get(r["employee"]) if r.get("employee") else None),
                "pickup_point": r.get("pickup_point"),
                "notes": r.get("notes"),
            }
        )
    return workers

def _registered_trip_workers(dispatch_trip, transport_request=None):
    """Return the de-duplicated worker manifest across all trip requests."""
    from apex.salis.api.boarding_flow import _manifest_request_names

    workers = []
    seen = set()
    for request in _manifest_request_names(dispatch_trip, transport_request):
        for worker in _registered_workers(request):
            employee = worker.get("employee")
            key = employee or (request, worker.get("pickup_point"), worker.get("notes"))
            if key in seen:
                continue
            seen.add(key)
            workers.append(worker)
    return workers

def _ordered_stops(parent, parenttype="Route Plan"):
    """Return ordered stops for one route-bearing document."""
    if not parent:
        return []
    rows = frappe.get_all(
        "Route Stop",
        filters={"parent": parent, "parenttype": parenttype},
        fields=[
            "name",
            "idx",
            "stop_key",
            "stop_name",
            "accommodation_building",
            "location",
            "planned_time",
            "passengers",
            "latitude",
            "longitude",
        ],
        order_by="idx asc",
    )
    bldg_ids = {r["accommodation_building"] for r in rows if r.get("accommodation_building")}
    buildings = (
        {
            b["name"]: b
            for b in frappe.get_all(
                "Building",
                filters={"name": ["in", list(bldg_ids)]},
                fields=["name", "building_name", "city", "district", "google_maps_url"],
            )
        }
        if bldg_ids
        else {}
    )
    stops = []
    for r in rows:
        building = None
        if r.get("accommodation_building"):
            b = buildings.get(r["accommodation_building"])
            if b:
                building = {
                    "name": b.get("name"),
                    "building_name": b.get("building_name"),
                    "city": b.get("city"),
                    "district": b.get("district"),
                    "google_maps_url": b.get("google_maps_url"),
                }
        stops.append(
            {
                "route_stop": r.get("name"),
                "stop_key": r.get("stop_key"),
                "stop_name": r.get("stop_name"),
                "sequence": r.get("idx"),
                "location": r.get("location"),
                "planned_time": _fmt_time(r.get("planned_time")),
                "expected_passengers": r.get("passengers"),
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "accommodation_building": r.get("accommodation_building"),
                "pickup": building,
            }
        )
    return stops

def _ordered_trip_stops(dispatch_trip, route_plan=None):
    """Read the immutable trip copy; use Route Plan only for legacy trips."""
    stops = _ordered_stops(dispatch_trip, "Dispatch Trip")
    if stops:
        return stops
    if not route_plan and dispatch_trip:
        route_plan = frappe.db.get_value("Dispatch Trip", dispatch_trip, "route_plan")
    return _ordered_stops(route_plan, "Route Plan")

def _is_upcoming_pickup(pickup_datetime, now_dt=None):
    """True when ``pickup_datetime`` (a backend string or datetime) is at or after
    ``now_dt`` (defaults to now). A missing pickup is treated as upcoming so a
    not-yet-scheduled request never silently drops off the worker's view."""
    if not pickup_datetime:
        return True
    now_dt = now_dt or frappe.utils.now_datetime()
    try:
        return frappe.utils.get_datetime(pickup_datetime) >= now_dt
    except Exception:
        return True

def _worker_pickup_stop(stops, my_building):
    """The worker's OWN pickup stop from the ordered route stops.

    Prefers the housing pickup whose ``accommodation_building`` matches the
    worker's active Accommodation Assignment building; falls back to the first
    housing pickup (a stop carrying any ``accommodation_building``); finally to
    the first stop. Returns None only for an empty route."""
    if not stops:
        return None
    if my_building:
        for s in stops:
            if s.get("accommodation_building") == my_building:
                return s
    for s in stops:
        if s.get("accommodation_building"):
            return s
    return stops[0]

def _route_destination_stop(stops, my_pickup):
    """The route's destination (final drop-off) stop.

    The drop-off is the last stop on the ordered route — the point AFTER every
    housing pickup. Returns None when the only stop is the worker's own pickup
    (a single-stop route has no separate destination to show)."""
    if not stops:
        return None
    last = stops[-1]
    if my_pickup is not None and last is my_pickup:
        return None
    return last

WORKER_TRANSPORT_HISTORY_DAYS = 90
WORKER_TRANSPORT_ROW_LIMIT = 200

def _worker_transport_requests(employee):
    """Transport Requests whose worker manifest includes ``employee``, scoped via the
    child table.

    Rejected and Cancelled are excluded; Fulfilled is included. It is the caller that
    partitions these rows into the worker's upcoming and past rides, so dropping
    Fulfilled would empty the past half of his screen.

    Bounded two ways so a long-tenured worker's 10-second poll cannot grow without
    limit: a floor of ``WORKER_TRANSPORT_HISTORY_DAYS`` on ``pickup_datetime`` (a
    request with no ``pickup_datetime`` yet is kept regardless — it has nothing to
    floor against and is usually the newest, unscheduled request), and a hard
    ``WORKER_TRANSPORT_ROW_LIMIT`` backstop. The floor only trims the PAST half;
    every upcoming ride is inside it by construction."""
    parents = frappe.get_all(
        "Transport Request Worker",
        filters={"employee": employee, "parenttype": "Transport Request"},
        fields=["parent", "pickup_point"],
    )
    by_request = {}
    for p in parents:
        by_request.setdefault(p["parent"], p.get("pickup_point"))
    if not by_request:
        return []
    since = frappe.utils.add_days(frappe.utils.today(), -WORKER_TRANSPORT_HISTORY_DAYS)
    rows = frappe.get_all(
        "Transport Request",
        filters={
            "name": ["in", list(by_request.keys())],
            "service_line": ["in", list(WORKER_SERVICE_LINES)],
            "status": ["not in", ["Rejected", "Cancelled"]],
        },
        or_filters=[
            ["pickup_datetime", ">=", since],
            ["pickup_datetime", "is", "not set"],
        ],
        fields=[
            "name",
            "service_line",
            "request_type",
            "project",
            "accommodation_building",
            "pickup_datetime",
            "status",
            "route_plan",
            "assigned_vehicle",
            "assigned_driver",
            "dispatch_trip",
        ],
        order_by="pickup_datetime asc",
        limit_page_length=WORKER_TRANSPORT_ROW_LIMIT,
    )
    for r in rows:
        r["pickup_point"] = by_request.get(r["name"])
    return rows

def _worker_today_dispatch_trip(employee, transport_request=None):
    """Resolve the ONE today's Dispatch Trip this worker may confirm boarding on.

    Resolved FORWARD from today's Dispatch Trips (Dispatch Trip -> Transport
    Request -> worker manifest), the same direction the driver QR scan and the
    driver route view resolve — NOT from the request's ``dispatch_trip``
    back-link, which is only stamped once a trip is Completed (a worker boards
    BEFORE completion). A trip qualifies only when its linked request carries
    THIS employee on its manifest, so the resolution can never reach a trip the
    worker is not on. A client-supplied ``transport_request`` only NARROWS that
    own-set; an id the worker is not registered on simply does not match. Returns
    ``(dispatch_trip, transport_request, stop_name, accommodation_building)`` or
    None when the worker has no boardable trip today.

    THE WORKER IS RESOLVED FIRST, and every read after it is keyed on that worker's
    own requests. Reading today's Dispatch Trips before narrowing meant a fleet-wide
    scan on a screen that polls every ten seconds, and the three later reads then
    fanned out over trips this worker was never on. The three links are unchanged —
    the trip's own ``transport_request``, an assigned-request child row, or the
    historical Route Plan's request — they are just resolved from the worker's side."""
    worker_pickup = {}
    for wrow in frappe.get_all(
        "Transport Request Worker",
        filters={"parenttype": "Transport Request", "employee": employee},
        fields=["parent", "pickup_point"],
        order_by="modified asc",
    ):
        worker_pickup.setdefault(wrow["parent"], wrow.get("pickup_point"))
    if not worker_pickup:
        return None

    own_requests = list(worker_pickup)

    assigned_by_trip = {}
    for arow in frappe.get_all(
        "Dispatch Trip Assigned Request",
        filters={
            "parenttype": "Dispatch Trip",
            "transport_request": ["in", own_requests],
        },
        fields=["parent", "transport_request"],
        order_by="idx asc",
    ):
        assigned_by_trip.setdefault(arow["parent"], []).append(arow["transport_request"])

    route_plan_req = {
        rp["name"]: rp["transport_request"]
        for rp in frappe.get_all(
            "Route Plan",
            filters={"transport_request": ["in", own_requests]},
            fields=["name", "transport_request"],
        )
    }

    reachable = [["transport_request", "in", own_requests]]
    if assigned_by_trip:
        reachable.append(["name", "in", list(assigned_by_trip)])
    if route_plan_req:
        reachable.append(["route_plan", "in", list(route_plan_req)])

    trips = frappe.get_all(
        "Dispatch Trip",
        filters={
            "trip_date": _trip_date_window(),
            "docstatus": ["<", 2],
            "status": ["not in", list(_FINISHED_TRIP_STATUSES)],
        },
        or_filters=reachable,
        fields=["name", "route_plan", "transport_request"],
        order_by="depart_time asc",
    )

    for t in trips:
        req = t.get("transport_request")
        if not req and t.get("route_plan"):
            req = route_plan_req.get(t["route_plan"])
        candidate_reqs = [req, *assigned_by_trip.get(t["name"], [])]
        if transport_request:
            candidate_reqs = [r for r in candidate_reqs if r == transport_request]
        for candidate in candidate_reqs:
            if not candidate:
                continue
            if candidate not in worker_pickup:
                continue
            building = frappe.db.get_value(
                "Transport Request", candidate, "accommodation_building"
            )
            return t["name"], candidate, worker_pickup[candidate], building
    return None
