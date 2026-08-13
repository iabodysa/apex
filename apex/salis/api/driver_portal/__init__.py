# Copyright (c) 2026, afmcoltd
"""Salis Driver Portal identity-scoped APIs for the mobile SPA at ``/driver``.

Every endpoint resolves a presented driver credential before using the legacy
signed-in preview path, then acts only on that driver's records. The client never
supplies a driver id.
"""

import frappe

from frappe import _

from apex.salis.api.maps_links import _full_route_maps_url as _chain_route_maps_url
from apex.salis.api.maps_links import _stop_waypoint  # noqa: F401
from apex.salis.utils import get_driver_for_user

def _portal_enabled():
    """Returns True when the driver portal is enabled in Salis Settings."""
    return bool(frappe.db.get_single_value("Salis Settings", "enable_driver_portal"))

def _find_driver(user=None):
    """Resolve the presented driver credential, else a linked preview user.

	Thin alias of the shared ``salis.utils.get_driver_for_user`` (the single
	resolver). Soft lookup with no exception — the portal bootstrap (and masar,
	which imports ``_resolve_driver``) relies on an unlinked user getting a
	friendly screen instead of a 403."""
    return get_driver_for_user(user)

def _resolve_driver(user=None):
    """Return the credential-resolved driver, else 403.

	A presented credential always wins over any signed-in preview user. Used by every
	action endpoint so writes are scoped to one active server-resolved driver."""
    driver = _find_driver(user)
    if not driver:
        frappe.throw(_("No Salis Driver is linked to your account."), frappe.PermissionError)
    return driver

def _require_enabled():
    """Blocks the request with a permission error when the driver portal is disabled."""
    if not _portal_enabled():
        frappe.throw(_("Driver portal is not enabled."), frappe.PermissionError)

def _label_trips(trips):
    """Swap route_plan / vehicle link ids for their human labels (Route Plan.
	route_name, Salis Vehicle.plate_number) so the driver's cards read names."""

    def labels(doctype, names, field):
        """Returns a map of document name to the given field's value for the given names."""
        if not names:
            return {}
        rows = frappe.get_all(
            doctype, filters={"name": ["in", list(names)]}, fields=["name", field]
        )
        return {r["name"]: r[field] for r in rows}

    plates = labels(
        "Salis Vehicle", {t.get("vehicle") for t in trips if t.get("vehicle")}, "plate_number"
    )
    routes = labels(
        "Route Plan", {t.get("route_plan") for t in trips if t.get("route_plan")}, "route_name"
    )
    for t in trips:
        if t.get("vehicle"):
            t["vehicle"] = plates.get(t["vehicle"], t["vehicle"])
        if t.get("route_plan"):
            t["route_plan"] = routes.get(t["route_plan"], t["route_plan"])

def _full_route_maps_url(route_plan):
    """A single Google Maps directions URL chaining a route plan's ordered stops,
	or None when fewer than two stops are navigable.

	Resolves the plan via masar's read-only ``_ordered_stops`` (so the sequence
	matches the route view exactly), then delegates to the shared list-based
	chainer so the driver's deep-link is identical to the worker's. Read-only."""
    from apex.salis.api import masar

    return _chain_route_maps_url(masar._ordered_stops(route_plan))

def _route_first_stop_maps_url(route_plan):
    """The Google Maps deep-link for a route plan's first mapped stop, or None.

	Reuses masar's read-only ``_ordered_stops`` so the URL is the exact one the
	Route screen already renders. Returns the first stop pickup that carries a
	``google_maps_url`` (the trip's first navigable destination), so a Trips/
	next-trip card can offer the same one-tap navigation. Read-only."""
    if not route_plan:
        return None
    from apex.salis.api import masar

    for stop in masar._ordered_stops(route_plan):
        pickup = stop.get("pickup") or {}
        if pickup.get("google_maps_url"):
            return pickup["google_maps_url"]
    return None

def _attach_trip_maps(trips):
    """Stamp each trip with ``google_maps_url`` (its first mapped stop's deep-link).
	Must run BEFORE ``_label_trips`` overwrites ``route_plan`` with the route name."""
    cache = {}
    for t in trips:
        rp = t.get("route_plan")
        if rp and rp not in cache:
            cache[rp] = _route_first_stop_maps_url(rp)
        t["google_maps_url"] = cache.get(rp)

def _attach_trip_log_state(trips, driver):
    """Stamp each trip card with its Trip Start Log state (started / log status) so the
	driver's Trips list can show start/complete without a per-card round-trip. One query
	keyed on the driver's logs for the listed trips; trips with no log read as not started."""
    names = [t["name"] for t in trips if t.get("name")]
    if not names:
        return
    logs = frappe.get_all(
        "Trip Start Log",
        filters={"dispatch_trip": ["in", names], "driver": driver, "docstatus": ["<", 2]},
        fields=["dispatch_trip", "status"],
    )
    by_trip = {row["dispatch_trip"]: row.get("status") for row in logs}
    for t in trips:
        status = by_trip.get(t["name"])
        t["started"] = t["name"] in by_trip
        t["trip_log_status"] = status

def _attach_boarding_counts(trips, driver):
    """Stamp each trip card with boarded / expected headcount for an "N of M boarded"
	progress line. ``boarded_count`` comes from the trip's Trip Start Log (the
	controller derives it from the boarding-event rows); ``expected_count`` is the
	linked Transport Request's manifest size — read directly so a trip with no log
	yet still shows "0 of M". One query per side keyed on the listed trips."""
    names = [t["name"] for t in trips if t.get("name")]
    if not names:
        return
    logs = frappe.get_all(
        "Trip Start Log",
        filters={"dispatch_trip": ["in", names], "driver": driver, "docstatus": ["<", 2]},
        fields=["dispatch_trip", "boarded_count"],
    )
    boarded_by_trip = {
        row["dispatch_trip"]: frappe.utils.cint(row.get("boarded_count")) for row in logs
    }
    requests = {t.get("transport_request") for t in trips if t.get("transport_request")}
    expected_by_request = {}
    if requests:
        for r in frappe.get_all(
            "Transport Request",
            filters={"name": ["in", list(requests)]},
            fields=["name", "worker_count"],
        ):
            expected_by_request[r["name"]] = frappe.utils.cint(r.get("worker_count"))
    for t in trips:
        t["boarded_count"] = boarded_by_trip.get(t["name"], 0)
        t["expected_count"] = expected_by_request.get(t.get("transport_request"), 0)

def _resolve_my_trip(dispatch_trip, driver):
    """The Dispatch Trip ``dispatch_trip`` only when it belongs to ``driver``, else
	fail closed. Shared scope guard for the trip-execution writes so one driver can
	never start/complete another driver's trip by guessing an id."""
    trip = frappe.db.get_value(
        "Dispatch Trip",
        {"name": dispatch_trip, "driver": driver},
        ["name", "vehicle", "route_plan", "transport_request", "trip_date", "status"],
        as_dict=True,
    )
    if not trip:
        frappe.throw(_("Trip not found."), frappe.DoesNotExistError)
    if trip.get("status") != "Dispatched":
        frappe.throw(_("Only a dispatched trip can be executed."))
    trip_date = frappe.utils.getdate(trip.get("trip_date")) if trip.get("trip_date") else None
    today = frappe.utils.getdate(frappe.utils.today())
    if trip_date and not (frappe.utils.add_days(today, -1) <= trip_date <= today):
        frappe.throw(_("This trip is not today's."))
    return trip


def _resolve_trip_route_stop(trip, route_stop):
    """Return one stop only when it belongs to the resolved trip's route plan."""
    stop = None
    if trip.get("route_plan") and route_stop:
        stop = frappe.db.get_value(
            "Route Stop",
            {
                "name": route_stop,
                "parent": trip.get("route_plan"),
                "parenttype": "Route Plan",
            },
            ["name", "idx", "stop_name"],
            as_dict=True,
        )
    if not stop:
        frappe.throw(
            _("Route stop is not part of this trip."),
            frappe.PermissionError,
        )
    return stop


def _open_trip_log(dispatch_trip, driver):
    """The driver's open (draft) Trip Start Log doc for a trip, or None. Stop progress
	is only kept on the live draft log — a submitted/cancelled log is closed."""
    name = frappe.db.get_value(
        "Trip Start Log",
        {"dispatch_trip": dispatch_trip, "driver": driver, "docstatus": 0},
        "name",
    )
    return frappe.get_doc("Trip Start Log", name) if name else None

def _stop_progress_map(dispatch_trip, driver):
    """``{route_stop: {done, done_at}}`` from the trip's open Trip Start Log, so the
	route view can reflect persisted per-stop completion on reload. Keyed on the source
	Route Stop row name (stable across reloads). Empty when the trip isn't started."""
    log = _open_trip_log(dispatch_trip, driver)
    if not log:
        return {}
    out = {}
    for row in log.stop_progress or []:
        if row.route_stop:
            out[row.route_stop] = {
                "done": bool(row.done),
                "done_at": frappe.utils.cstr(row.done_at) if row.done_at else None,
                "arrived": bool(row.arrived),
                "arrived_at": frappe.utils.cstr(row.arrived_at) if row.arrived_at else None,
            }
    return out

def _route_stop_names(route_plan):
    """The Route Stop child row names for a plan, in the SAME order masar._ordered_stops
	returns its stops (idx asc) — so they zip 1:1 onto that list to give each
	stop a stable identity for progress tracking. masar drops the row name, so it is
	re-fetched here. Read-only."""
    if not route_plan:
        return []
    return frappe.get_all(
        "Route Stop",
        filters={"parent": route_plan, "parenttype": "Route Plan"},
        pluck="name",
        order_by="idx asc",
    )

def _attach_stop_progress(stops, route_plan, dispatch_trip, driver):
    """Stamp each ordered stop with its ``route_stop`` (stable Route Stop row name) and
	persisted ``done``/``done_at`` from the trip's open Trip Start Log. Mutates in place;
	a not-started trip leaves every stop ``done=False``."""
    if not stops:
        return
    names = _route_stop_names(route_plan)
    progress = _stop_progress_map(dispatch_trip, driver)
    for i, stop in enumerate(stops):
        rs = names[i] if i < len(names) else None
        stop["route_stop"] = rs
        state = progress.get(rs) if rs else None
        stop["done"] = bool(state and state.get("done"))
        stop["done_at"] = state.get("done_at") if state else None
        stop["arrived"] = bool(state and state.get("arrived"))
        stop["arrived_at"] = state.get("arrived_at") if state else None


from apex.salis.api.driver_portal.profile import (  # noqa: E402
    get_driver_profile,
)
from apex.salis.api.driver_portal.trips import (  # noqa: E402
    my_trips_today,
    my_trips_recent,
    my_worker_route_today,
    my_trip_route,
)
from apex.salis.api.driver_portal.execution import (  # noqa: E402
    start_my_trip,
    complete_my_trip,
    mark_stop_progress,
)
