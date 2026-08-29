# Copyright (c) 2026, afmcoltd

import frappe

from frappe import _

from apex.salis.api.maps_links import _full_route_maps_url as _chain_route_maps_url
from apex.salis.api.maps_links import _stop_waypoint
from apex.apex_core.doctype.portal_device.portal_device import apply_device_language
from apex.apex_core.utils.portal_identity import DRIVER
from apex.salis.utils import get_driver_for_user

def _resolve_driver(user=None):
    driver = get_driver_for_user(user)
    if not driver:
        frappe.throw(_("No Salis Driver is linked to your account."), frappe.PermissionError)
    return driver

def _require_enabled():
    apply_device_language(DRIVER)
    if not frappe.db.get_single_value("Salis Settings", "enable_driver_portal"):
        frappe.throw(_("Driver portal is not enabled."), frappe.PermissionError)

def _label_trips(trips):

    def labels(doctype, names, field):
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
    from apex.salis.api import masar

    return _chain_route_maps_url(masar._ordered_trip_stops(dispatch_trip, route_plan))

def _attach_trip_log_state(trips, driver):
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
    for row in frappe.get_list(
        "Trip Boarding State",
        filters={"parent": ["in", names], "parenttype": "Dispatch Trip"},
        fields=["parent"],
        parent_doctype="Dispatch Trip",
    ):
        expected_by_trip[row["parent"]] += 1
    for t in trips:
        t["boarded_count"] = boarded_by_trip.get(t["name"], 0)
        t["expected_count"] = expected_by_trip.get(t["name"], 0)

def _resolve_my_trip(dispatch_trip, driver):
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
    name = frappe.db.get_value(
        "Trip Start Log",
        {"dispatch_trip": dispatch_trip, "driver": driver, "docstatus": 0},
        "name",
    )
    return frappe.get_doc("Trip Start Log", name) if name else None

def _stop_progress_map(dispatch_trip, driver):
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
