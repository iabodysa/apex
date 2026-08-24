# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _

from apex.apex_core.utils.portal_identity import DRIVER, as_capacity
from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.salis.api.boarding_flow import (
    _manifest_employees,
    _manifest_employees_for_stop,
    _publish,
    ensure_trip_boarding_state,
)
from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
    _resolve_my_trip,
    _resolve_trip_route_stop,
    _open_trip_log,
    _stop_progress_map,
)


def _trip_log_state(driver, dispatch_trip):
    log = frappe.db.get_value(
        "Trip Start Log",
        {"dispatch_trip": dispatch_trip, "driver": driver, "docstatus": ["<", 2]},
        ["name", "status", "start_datetime", "end_datetime"],
        as_dict=True,
    )
    if not log:
        return {"started": False, "trip_log_status": None, "start_datetime": None, "end_datetime": None}
    return {
        "started": True,
        "name": log["name"],
        "trip_log_status": log.get("status"),
        "start_datetime": frappe.utils.cstr(log["start_datetime"]) if log.get("start_datetime") else None,
        "end_datetime": frappe.utils.cstr(log["end_datetime"]) if log.get("end_datetime") else None,
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def start_my_trip(dispatch_trip):
    _require_enabled()
    driver = _resolve_driver()
    trip = _resolve_my_trip(dispatch_trip, driver)
    existing = frappe.db.get_value(
        "Trip Start Log",
        {"dispatch_trip": dispatch_trip, "driver": driver, "docstatus": ["<", 2]},
        "name",
    )
    if not existing:
        doc = frappe.get_doc(
            {
                "doctype": "Trip Start Log",
                "dispatch_trip": dispatch_trip,
                "driver": driver,
                "vehicle": trip.get("vehicle"),
                "trip_date": trip.get("trip_date") or frappe.utils.today(),
                "status": "Started",
                "start_datetime": frappe.utils.now_datetime(),
            }
        )
        with as_capacity(DRIVER, driver):
            doc.insert()
    ensure_trip_boarding_state(dispatch_trip)
    _publish(
        "driver_trip_update",
        dispatch_trip,
        {"status": "Started"},
        driver=driver,
        employees=_manifest_employees(dispatch_trip),
    )
    return _trip_log_state(driver, dispatch_trip)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def complete_my_trip(dispatch_trip):
    _require_enabled()
    driver = _resolve_driver()
    trip = _resolve_my_trip(dispatch_trip, driver)
    name = frappe.db.get_value(
        "Trip Start Log",
        {"dispatch_trip": dispatch_trip, "driver": driver, "docstatus": ["<", 2]},
        "name",
    )
    if name:
        doc = frappe.get_doc("Trip Start Log", name)
    else:
        doc = frappe.get_doc(
            {
                "doctype": "Trip Start Log",
                "dispatch_trip": dispatch_trip,
                "driver": driver,
                "vehicle": trip.get("vehicle"),
                "trip_date": trip.get("trip_date") or frappe.utils.today(),
                "start_datetime": frappe.utils.now_datetime(),
            }
        )
    doc.status = "Completed"
    if not doc.end_datetime:
        doc.end_datetime = frappe.utils.now_datetime()
    with as_capacity(DRIVER, driver):
        doc.save() if not doc.is_new() else doc.insert()
    _publish(
        "driver_trip_update",
        dispatch_trip,
        {"status": "Completed"},
        driver=driver,
        employees=_manifest_employees(dispatch_trip),
    )
    return _trip_log_state(driver, dispatch_trip)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def mark_stop_progress(dispatch_trip, route_stop, done=1, sequence=None, stop_name=None):
    _require_enabled()
    driver = _resolve_driver()
    trip = _resolve_my_trip(dispatch_trip, driver)
    stop = _resolve_trip_route_stop(trip, route_stop)
    log = _open_trip_log(dispatch_trip, driver)
    if not log:
        frappe.throw(_("Start the trip before marking stops."))

    done = frappe.utils.cint(done)
    existing = next((r for r in (log.stop_progress or []) if r.route_stop == route_stop), None)
    if existing:
        existing.sequence = stop.get("idx")
        existing.stop_name = stop.get("stop_name")
        existing.done = done
        existing.done_at = frappe.utils.now_datetime() if done else None
    else:
        log.append(
            "stop_progress",
            {
                "route_stop": route_stop,
                "sequence": stop.get("idx"),
                "stop_name": stop.get("stop_name"),
                "done": done,
                "done_at": frappe.utils.now_datetime() if done else None,
            },
        )
    with as_capacity(DRIVER, driver):
        log.save()
    return {
        "route_stop": route_stop,
        "done": bool(done),
        "stop_progress": _stop_progress_map(dispatch_trip, driver),
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def mark_arrived(dispatch_trip, route_stop):
    _require_enabled()
    driver = _resolve_driver()
    trip = _resolve_my_trip(dispatch_trip, driver)
    stop = _resolve_trip_route_stop(trip, route_stop)
    log = _open_trip_log(dispatch_trip, driver)
    if not log:
        frappe.throw(_("Start the trip before marking arrival."))

    row = next((item for item in (log.stop_progress or []) if item.route_stop == route_stop), None)
    now = frappe.utils.now_datetime()
    if row:
        row.sequence = stop.get("idx")
        row.stop_name = stop.get("stop_name")
        row.arrived = 1
        row.arrived_at = now
    else:
        log.append(
            "stop_progress",
            {
                "route_stop": route_stop,
                "sequence": stop.get("idx"),
                "stop_name": stop.get("stop_name"),
                "arrived": 1,
                "arrived_at": now,
            },
        )
    with as_capacity(DRIVER, driver):
        log.save()
    _publish(
        "boarding_arrived",
        dispatch_trip,
        {"route_stop": route_stop},
        driver=driver,
        employees=_manifest_employees_for_stop(dispatch_trip, route_stop),
    )
    return {
        "route_stop": route_stop,
        "arrived": True,
        "stop_progress": _stop_progress_map(dispatch_trip, driver),
    }
