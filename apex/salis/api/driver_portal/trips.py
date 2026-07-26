# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver Portal — trips endpoints (split from the driver_portal god module in P-180). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
    _label_trips,
    _full_route_maps_url,
    _attach_trip_maps,
    _attach_trip_log_state,
    _attach_boarding_counts,
    _attach_stop_progress,
)


RECENT_TRIP_DEFAULT_DAYS = 30
RECENT_TRIP_MAX_DAYS = 90
RECENT_TRIP_DEFAULT_LIMIT = 50
RECENT_TRIP_MAX_LIMIT = 100


def _bounded_positive(value, default, maximum):
	parsed = frappe.utils.cint(value)
	if parsed <= 0:
		return default
	return min(parsed, maximum)


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def my_trips_today():
	"""Today's Dispatch Trips for the current driver (read)."""
	_require_enabled()
	driver = _resolve_driver()
	trips = frappe.get_all(
		"Dispatch Trip",
		filters={"driver": driver, "trip_date": frappe.utils.today()},
		fields=["name", "route_plan", "vehicle", "transport_request", "depart_time", "return_time", "status"],
		order_by="depart_time asc",
	)
	_attach_trip_maps(trips)  # [#c8i03i]
	_label_trips(trips)  # [#jlry93]
	_attach_trip_log_state(trips, driver)  # [#qu3kwf]
	_attach_boarding_counts(trips, driver)  # [#d6x6zw]
	return trips



@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def my_trips_recent(days=30, limit=50):
	"""The current driver's recent Dispatch Trips, newest first (read).

	Identity-scoped via endpoint-scoped ``get_all`` (the ``my_trips_today``
	precedent): the driver is resolved credential-first and every row is filtered
	on that driver, so this can only return the caller's own trips. Backs the Trips
	view's "recent/past" tab while ``my_trips_today`` stays the default — the SPA
	switches endpoints, the card shape is identical (route/vehicle link ids swapped
	for human labels by the same ``_label_trips``).

	``days`` bounds the window (trip_date >= today - days; defaults to 30) and
	``limit`` caps the rows, so the list never grows unbounded for a long-tenured
	driver. ``trip_date`` is included (and stringified) so the SPA can group/sort by
	day. Read-only, no commit."""
	_require_enabled()
	driver = _resolve_driver()
	days = _bounded_positive(days, RECENT_TRIP_DEFAULT_DAYS, RECENT_TRIP_MAX_DAYS)
	limit = _bounded_positive(limit, RECENT_TRIP_DEFAULT_LIMIT, RECENT_TRIP_MAX_LIMIT)
	since = frappe.utils.add_days(frappe.utils.today(), -days)
	trips = frappe.get_all(
		"Dispatch Trip",
		filters={"driver": driver, "trip_date": [">=", since]},
		fields=["name", "trip_date", "route_plan", "vehicle", "depart_time", "return_time", "status"],
		order_by="trip_date desc, depart_time desc",
		limit=limit,
	)
	_attach_trip_maps(trips)  # [#c8i03i]
	_label_trips(trips)  # [#jlry93]
	for t in trips:
		t["trip_date"] = frappe.utils.cstr(t["trip_date"]) if t.get("trip_date") else None
	return trips



def _worker_phone(employee):
    """The worker's contact number for a one-tap call, or None. Reads the Employee's
    ``cell_number`` (the manifest's call target); a missing number simply omits the
    call action. Read-only."""
    if not employee:
        return None
    return frappe.db.get_value("Employee", employee, "cell_number") or None



def _enrich_workers_with_phone(workers):
    """Stamp each manifest worker dict with a ``phone`` for the tel: call action.
    Mutates in place. One get per employee (the manifests are small)."""
    for w in workers or []:
        if "phone" not in w:
            w["phone"] = _worker_phone(w.get("employee"))



@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def my_worker_route_today():
    """The current driver's worker-transport route today (read), surfaced in the
    driver portal's "My Route" screen.

    Identity-scoped wrapper over ``salis.api.masar.get_my_worker_route_today``
    (which resolves driver credentials before any session fallback). Lives here so
    the driver SPA calls one cohesive driver-portal API namespace. Augments each
    trip's registered worker manifest with the worker's ``phone`` so the portal can
    offer a one-tap call; masar is imported (read-only), not edited. Read-only."""
    from apex.salis.api import masar

    data = masar.get_my_worker_route_today()
    for trip in data.get("trips", []):
        _enrich_workers_with_phone(trip.get("workers"))
        trip["maps_route_url"] = _full_route_maps_url(trip.get("route_plan"))
    return data



@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def my_trip_route(dispatch_trip):
    """One trip's ordered route for the current driver (read).

    Backs the driver portal's per-trip drill-in: tapping a "My Trips" card opens
    this single Dispatch Trip's ordered stops. Identity-scoped — the driver is
    resolved credential-first, never client-supplied — and the trip is returned
    only when it belongs to that driver, so one driver can never read another's
    trip by guessing a ``dispatch_trip`` id.

    Reuses masar's read-only stop-ordering (``_ordered_stops``) so the timeline
    shape matches the all-trips route view exactly; masar is imported, not edited.
    A trip with no ``route_plan`` (e.g. an Administrative Trip, excluded from the
    worker route) returns ``has_route_plan = False`` with an empty ``stops`` list,
    letting the SPA show an explicit "no route planned" state rather than a blank.
    Read-only, no commit, no GL."""
    _require_enabled()
    driver = _resolve_driver()

    trip = frappe.db.get_value(
        "Dispatch Trip",
        {"name": dispatch_trip, "driver": driver},
        ["name", "route_plan", "vehicle", "transport_request", "depart_time", "return_time", "status"],
        as_dict=True,
    )
    # [#qg5cw1]
    if not trip:
        frappe.throw(_("Trip not found."), frappe.DoesNotExistError)

    from apex.salis.api import masar

    route_plan = trip.get("route_plan")
    stops = masar._ordered_stops(route_plan)  # [#492z2y]
    # [#ja9fyd]
    _attach_stop_progress(stops, route_plan, trip["name"], driver)

    # [#j3iz55]
    workers = masar._registered_workers(trip.get("transport_request"))  # [#ba2aen]
    _enrich_workers_with_phone(workers)

    vehicle = trip.get("vehicle")
    if vehicle:
        vehicle = frappe.db.get_value("Salis Vehicle", vehicle, "plate_number") or vehicle

    return {
        "dispatch_trip": trip["name"],
        "route_plan": route_plan,
        "route_name": (
            (frappe.db.get_value("Route Plan", route_plan, "route_name") or route_plan)
            if route_plan
            else None
        ),
        "vehicle": vehicle,
        "depart_time": masar._fmt_time(trip.get("depart_time")),
        "return_time": masar._fmt_time(trip.get("return_time")),
        "status": trip.get("status"),
        "has_route_plan": bool(route_plan),
        # [#mis85h]
        "started": bool(
            frappe.db.exists(
                "Trip Start Log",
                {"dispatch_trip": trip["name"], "driver": driver, "docstatus": 0},
            )
        ),
        "stops": stops,
        "workers": workers,
        "expected_count": len(workers),
        "maps_route_url": _full_route_maps_url(route_plan),
    }
