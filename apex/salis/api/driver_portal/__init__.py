# Copyright (c) 2026, afmcoltd
"""Salis Driver Portal identity-scoped APIs for the mobile SPA at ``/driver``.

Every endpoint resolves a presented driver credential before using the legacy
signed-in preview path, then acts only on that driver's records. The client never
supplies a driver id.
"""

import frappe

from frappe import _

from apex.salis.api.maps_links import _full_route_maps_url as _chain_route_maps_url
from apex.salis.api.maps_links import _stop_waypoint
from apex.salis.utils import get_driver_for_user

def _resolve_driver(user=None):
    """Return the credential-resolved driver, else 403.

	A presented credential always wins over any signed-in preview user. Used by every
	action endpoint so writes are scoped to one active server-resolved driver. Soft
	lookup with no exception on the resolve itself — the portal bootstrap (and masar,
	which imports this function) relies on an unlinked user getting a friendly screen
	instead of a 403, which this function then raises for its own callers."""
    driver = get_driver_for_user(user)
    if not driver:
        frappe.throw(_("No Salis Driver is linked to your account."), frappe.PermissionError)
    return driver

def _require_enabled():
    """Open the driver-portal request: pin its language, then block a disabled portal.

    The language pin lives here because this is the request PREAMBLE — the first
    statement of every ``/driver`` endpoint, ``manual_boarding.board_worker``
    included — not because it is a permission concern. The shell at
    ``apex/www/driver.py`` already sets the render language for the page,
    but each endpoint the SPA then calls is its own request: a driver is Guest, so
    ``frappe.translate.get_language`` falls through to the phone's Accept-Language
    header or System Settings (``frappe/translate.py:35-60``) and painted English
    refusals inside an Arabic RTL screen. The portal declares one language in its
    own markup; this makes the API it calls agree.
    """
    frappe.local.lang = "ar"
    if not frappe.db.get_single_value("Salis Settings", "enable_driver_portal"):
        frappe.throw(_("Driver portal is not enabled."), frappe.PermissionError)

def _label_trips(trips):
    """Attach human trip and vehicle labels without replacing link ids."""

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
    legacy_routes = labels(
        "Route Plan",
        {
            t.get("route_plan")
            for t in trips
            if t.get("route_plan") and not t.get("trip_title")
        },
        "route_name",
    )
    for t in trips:
        if t.get("vehicle"):
            t["vehicle"] = plates.get(t["vehicle"], t["vehicle"])
        t["route_name"] = (
            t.get("trip_title")
            or legacy_routes.get(t.get("route_plan"))
            or t.get("name")
        )

def _trip_route_maps_url(dispatch_trip, route_plan=None):
    """Build directions from the actual trip stops, with legacy fallback."""
    from apex.salis.api import masar

    return _chain_route_maps_url(masar._ordered_trip_stops(dispatch_trip, route_plan))

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
    """Attach boarded and expected passenger counts."""
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
    expected_by_trip = {name: 0 for name in names}
    for row in frappe.get_all(
        "Trip Boarding State",
        filters={"parent": ["in", names], "parenttype": "Dispatch Trip"},
        fields=["parent"],
    ):
        expected_by_trip[row["parent"]] += 1
    for t in trips:
        t["boarded_count"] = boarded_by_trip.get(t["name"], 0)
        t["expected_count"] = expected_by_trip.get(t["name"], 0)

def _resolve_my_trip(dispatch_trip, driver):
    """The Dispatch Trip ``dispatch_trip`` only when it belongs to ``driver``, else
	fail closed. Shared scope guard for the trip-execution writes so one driver can
	never start/complete another driver's trip by guessing an id."""
    trip = frappe.db.get_value(
        "Dispatch Trip",
        {"name": dispatch_trip, "driver": driver},
        [
            "name",
            "trip_title",
            "vehicle",
            "route_assignment",
            "route_template",
            "route_plan",
            "transport_request",
            "trip_date",
            "status",
        ],
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
    """Return a stop from the actual trip; permit legacy rows only when needed."""
    stop = None
    if trip.get("name") and route_stop:
        stop = frappe.db.get_value(
            "Route Stop",
            {
                "name": route_stop,
                "parent": trip.get("name"),
                "parenttype": "Dispatch Trip",
            },
            ["name", "idx", "stop_name"],
            as_dict=True,
        )
    has_actual_stops = bool(
        trip.get("name")
        and frappe.db.exists(
            "Route Stop",
            {"parent": trip.get("name"), "parenttype": "Dispatch Trip"},
        )
    )
    if not stop and not has_actual_stops and trip.get("route_plan") and route_stop:
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

def _attach_stop_progress(stops, dispatch_trip, driver):
    """Attach persisted progress using each copied stop's child-row id."""
    if not stops:
        return
    progress = _stop_progress_map(dispatch_trip, driver)
    for stop in stops:
        rs = stop.get("route_stop")
        state = progress.get(rs) if rs else None
        stop["done"] = bool(state and state.get("done"))
        stop["done_at"] = state.get("done_at") if state else None
        stop["arrived"] = bool(state and state.get("arrived"))
        stop["arrived_at"] = state.get("arrived_at") if state else None

from apex.salis.api.driver_portal.profile import (
    get_driver_profile,
)
from apex.salis.api.driver_portal.trips import (
    my_trips_today,
    my_trips_recent,
    my_worker_route_today,
    my_trip_route,
)
from apex.salis.api.driver_portal.execution import (
    start_my_trip,
    complete_my_trip,
    mark_arrived,
    mark_stop_progress,
)
