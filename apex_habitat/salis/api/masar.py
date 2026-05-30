"""Masar (Worker Movement) driver-portal read APIs.

Masar is the **Workers division of Salis** — the worker-transport experience on
the shared fleet backbone. This module serves the worker-transport *trip view*
for the CURRENT driver: today's worker route, its ordered stops (the "trip road"),
and the per-stop manifest (registered workers + each stop's Habitat housing
pickup).

Every endpoint resolves the session user to a Salis Driver server-side (reusing
the driver-portal identity pattern); the client never supplies a driver id, and
nothing here writes — it is read-only and feeds the future Phase 1b worker-view
UI inside the existing /driver portal. No GL, no side-effects.
"""

import frappe

from apex_habitat.salis.api.driver_portal import _require_enabled, _resolve_driver

# Worker-transport requests are the Workers service line.
WORKER_SERVICE_LINE = "Workers"


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


def _today_worker_trips(driver):
    """Today's Dispatch Trips for ``driver`` whose linked Transport Request is on
    the Workers service line. Returns a list of trip dicts with the route_plan and
    transport_request resolved, ordered by departure time."""
    trips = frappe.get_all(
        "Dispatch Trip",
        filters={
            "driver": driver,
            "trip_date": frappe.utils.today(),
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
    worker_trips = []
    for t in trips:
        # The Dispatch Trip's transport_request is a read-only fetch from its
        # Route Plan; resolve it through the route plan if the fetch left it blank
        # so service-line filtering and the manifest lookup stay reliable.
        if not t.get("transport_request") and t.get("route_plan"):
            t["transport_request"] = frappe.db.get_value(
                "Route Plan", t["route_plan"], "transport_request"
            )
        service_line = None
        if t.get("transport_request"):
            service_line = frappe.db.get_value(
                "Transport Request", t["transport_request"], "service_line"
            )
        if service_line == WORKER_SERVICE_LINE:
            worker_trips.append(t)
    return worker_trips


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
    workers = []
    for r in rows:
        workers.append(
            {
                "employee": r.get("employee"),
                "employee_name": (
                    frappe.db.get_value("Employee", r["employee"], "employee_name")
                    if r.get("employee")
                    else None
                ),
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
            "sequence",
            "stop_name",
            "accommodation_building",
            "location",
            "planned_time",
            "passengers",
        ],
        order_by="sequence asc, idx asc",
    )
    stops = []
    for r in rows:
        building = None
        if r.get("accommodation_building"):
            b = frappe.db.get_value(
                "Accommodation Building",
                r["accommodation_building"],
                ["name", "building_name", "city", "district", "google_maps_url"],
                as_dict=True,
            )
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
                "sequence": r.get("sequence"),
                "location": r.get("location"),
                "planned_time": _fmt_time(r.get("planned_time")),
                "expected_passengers": r.get("passengers"),
                "accommodation_building": r.get("accommodation_building"),
                "pickup": building,
            }
        )
    return stops


@frappe.whitelist()
def get_my_worker_route_today():
    """Read-only worker-transport trip view for the CURRENT driver.

    Resolves the session user to a Salis Driver server-side (no client-supplied
    id) and returns today's Workers-line route(s): for each trip, the route plan,
    its ordered stops (each with its Habitat housing pickup when linked), and the
    registered worker manifest carried by the linked Transport Request.

    Read-only. This feeds the future driver-portal worker view (Phase 1b); it
    posts no GL and writes nothing.

    Shape::

        {
          "driver": "DRV-000001",
          "date": "2026-05-30",
          "trips": [
            {
              "dispatch_trip": "DT-000007",
              "transport_request": "TR-000005",
              "route_plan": "RP-000005",
              "vehicle": "...", "depart_time": "06:30:00",
              "return_time": null, "status": "Planned",
              "expected_count": 3,
              "stops": [ { "stop_name": "...", "sequence": 1,
                           "accommodation_building": "...",
                           "pickup": { "building_name": "...", "city": "...",
                                       "google_maps_url": "..." } }, ... ],
              "workers": [ { "employee": "...", "employee_name": "...",
                             "pickup_point": "..." }, ... ]
            }
          ]
        }
    """
    _require_enabled()
    driver = _resolve_driver()
    trips = []
    for t in _today_worker_trips(driver):
        workers = _registered_workers(t.get("transport_request"))
        trips.append(
            {
                "dispatch_trip": t["name"],
                "transport_request": t.get("transport_request"),
                "route_plan": t.get("route_plan"),
                "vehicle": t.get("vehicle"),
                "depart_time": _fmt_time(t.get("depart_time")),
                "return_time": _fmt_time(t.get("return_time")),
                "status": t.get("status"),
                "expected_count": len(workers),
                "stops": _ordered_stops(t.get("route_plan")),
                "workers": workers,
            }
        )
    return {"driver": driver, "date": frappe.utils.today(), "trips": trips}
