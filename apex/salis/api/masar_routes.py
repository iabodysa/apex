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

_EARTH_RADIUS_KM = 6371.0088
_DEFAULT_FLEET_SPEED_KMPH = 40.0

_FINISHED_TRIP_STATUSES = boarding_window.FINISHED_TRIP_STATUSES


def _haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in km between two WGS-84 points. Pure math, no I/O."""
    import math

    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def _assumed_fleet_speed_kmph():
    """Assumed average fleet speed (km/h) for the ETA, from Salis Settings via the
    zero-trap reader (a blank/0 Single value falls back to the built-in default)."""
    from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_float

    return get_salis_float("assumed_fleet_speed_kmph", _DEFAULT_FLEET_SPEED_KMPH)


def _pickup_building_of(trip):
    """The Accommodation Building id the ETA targets for a worker's ride: the
    worker's OWN pickup stop's building. None when the ride has no housing pickup
    resolved (the ETA is then simply omitted)."""
    my_pickup = trip.get("my_pickup") or {}
    return my_pickup.get("accommodation_building")


def _live_dispatch_trip(transport_request):
    """The Dispatch Trip a worker's request is riding on RIGHT NOW — status
    Dispatched, driver en route. The Transport Request's own ``dispatch_trip`` link
    is stamped only at fulfilment (Completed), so during the en-route window — the
    exact time the live ETA is wanted — resolve the active trip directly by its
    back-link + live status. None when no trip is currently dispatched."""
    return frappe.db.get_value(
        "Dispatch Trip",
        {"transport_request": transport_request, "status": "Dispatched", "docstatus": ["<", 2]},
        "name",
    )


def compute_ride_eta_minutes(dispatch_trip, pickup_building):
    """Minutes until the driver reaches ``pickup_building``, from the trip's last
    stored driver GPS position — or None when the ETA cannot be computed.

    Self-contained: haversine(driver → pickup) / assumed fleet speed. Returns None
    (never raises) when the trip has no live position, the pickup building has no
    coordinates, or the speed is non-positive — the caller omits the ETA cleanly.
    Rounds to whole minutes; a driver already at the pickup yields 0."""
    if not dispatch_trip or not pickup_building:
        return None
    pos = frappe.db.get_value(
        "Dispatch Trip", dispatch_trip, ["driver_lat", "driver_lng"], as_dict=True
    )
    if not pos or pos.get("driver_lat") is None or pos.get("driver_lng") is None:
        return None
    dest = frappe.db.get_value(
        "Building", pickup_building, ["pickup_lat", "pickup_lng"], as_dict=True
    )
    if not dest or dest.get("pickup_lat") is None or dest.get("pickup_lng") is None:
        return None
    if not (pos.get("driver_lat") or pos.get("driver_lng")):
        return None
    if not (dest.get("pickup_lat") or dest.get("pickup_lng")):
        return None
    speed = _assumed_fleet_speed_kmph()
    if speed <= 0:
        return None
    distance_km = _haversine_km(
        pos["driver_lat"], pos["driver_lng"], dest["pickup_lat"], dest["pickup_lng"]
    )
    return int(round((distance_km / speed) * 60))


def _fmt_time(value):
    """Render a Time field as a clean zero-padded ``HH:MM:SS`` string (or None).

    Frappe stores Time as a ``datetime.timedelta``; ``cstr`` on it yields an
    unpadded value with stray microseconds (e.g. ``6:30:00`` /
    ``2:05:46.198544``). ``format_time`` normalises it to ``06:30:00`` for a clean
    JSON payload."""
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
            "docstatus": ["<", 2],
        },
        fields=[
            "name",
            "route_plan",
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
    rp_ids = {t["route_plan"] for t in trips if not t.get("transport_request") and t.get("route_plan")}
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

    tr_ids = {t["transport_request"] for t in trips if t.get("transport_request")}
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
    return [t for t in trips if service_lines.get(t.get("transport_request")) in WORKER_SERVICE_LINES]


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


def _ordered_stops(route_plan):
    """The ordered Route Stop rows for a Route Plan, each enriched with its Habitat
    pickup (Accommodation Building) details when the stop is a housing pickup."""
    if not route_plan:
        return []
    rows = frappe.get_all(
        "Route Stop",
        filters={"parent": route_plan, "parenttype": "Route Plan"},
        fields=[
            "name",
            "idx",
            "stop_name",
            "accommodation_building",
            "location",
            "planned_time",
            "passengers",
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
                "stop_name": r.get("stop_name"),
                "sequence": r.get("idx"),
                "location": r.get("location"),
                "planned_time": _fmt_time(r.get("planned_time")),
                "expected_passengers": r.get("passengers"),
                "accommodation_building": r.get("accommodation_building"),
                "pickup": building,
            }
        )
    return stops


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


def _worker_transport_requests(employee):
    """Transport Requests whose worker manifest includes ``employee`` and that are
    still live (not Rejected/Cancelled/Fulfilled). Scoped via the child table."""
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
    rows = frappe.get_all(
        "Transport Request",
        filters={
            "name": ["in", list(by_request.keys())],
            "service_line": ["in", list(WORKER_SERVICE_LINES)],
            "status": ["not in", ["Rejected", "Cancelled"]],
        },
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
    None when the worker has no boardable trip today."""
    trips = frappe.get_all(
        "Dispatch Trip",
        filters={
            "trip_date": _trip_date_window(),
            "docstatus": ["<", 2],
            "status": ["not in", list(_FINISHED_TRIP_STATUSES)],
        },
        fields=["name", "route_plan", "transport_request"],
        order_by="depart_time asc",
    )
    if not trips:
        return None

    trip_names = [t["name"] for t in trips]

    assigned_by_trip = {}
    for arow in frappe.get_all(
        "Dispatch Trip Assigned Request",
        filters={"parent": ["in", trip_names], "parenttype": "Dispatch Trip"},
        fields=["parent", "transport_request"],
        order_by="idx asc",
    ):
        assigned_by_trip.setdefault(arow["parent"], []).append(arow["transport_request"])

    route_plan_names = [
        t["route_plan"] for t in trips if not t.get("transport_request") and t.get("route_plan")
    ]
    route_plan_req = {}
    if route_plan_names:
        for rp in frappe.get_all(
            "Route Plan",
            filters={"name": ["in", route_plan_names]},
            fields=["name", "transport_request"],
        ):
            route_plan_req[rp["name"]] = rp["transport_request"]

    worker_pickup = {}
    for wrow in frappe.get_all(
        "Transport Request Worker",
        filters={"parenttype": "Transport Request", "employee": employee},
        fields=["parent", "pickup_point"],
        order_by="modified asc",
    ):
        worker_pickup.setdefault(wrow["parent"], wrow.get("pickup_point"))

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
