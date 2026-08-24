# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, time_diff_in_seconds

from apex.apex_core.utils.portal_identity import (
    DRIVER,
    WORKER,
    as_capacity,
    publish_to_portal_subject,
)
from apex.apex_core.utils.portal_live import notify_doctype
from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.apex_core.doctype.salis_settings.salis_settings import (
    get_boarding_setting,
)
from apex.salis.api import boarding, boarding_window
from apex.salis.api.web_push import enqueue_boarding_event


_MISBOARD_CACHE_PREFIX = "salis_misboard:"
_MISBOARD_TTL_SECONDS = 30 * 60


def _publish(event, dispatch_trip, payload, driver=None, employee=None, employees=None):
    body = {"dispatch_trip": dispatch_trip, **payload}
    try:
        notify_doctype("Dispatch Trip", event, body)
    except Exception:
        pass
    worker_subjects = [employee] if employee else []
    if employees:
        worker_subjects.extend(employees)
    audiences = [(DRIVER, driver), *((WORKER, subject) for subject in dict.fromkeys(worker_subjects))]
    for audience, subject in audiences:
        if not subject:
            continue
        try:
            publish_to_portal_subject(audience, subject, event, body)
        except Exception:
            pass
    try:
        enqueue_boarding_event(
            event,
            dispatch_trip,
            driver=driver,
            employees=worker_subjects,
            payload=payload,
        )
    except Exception:
        frappe.log_error(title="Boarding push enqueue failed")


def _request_workers(transport_request):
    if not transport_request:
        return []
    return frappe.get_all(
        "Transport Request Worker",
        filters={"parent": transport_request, "parenttype": "Transport Request"},
        pluck="employee",
        order_by="idx asc",
    )


def _assigned_request_names(dispatch_trip):
    if not dispatch_trip:
        return []
    return frappe.get_all(
        "Dispatch Trip Assigned Request",
        filters={"parent": dispatch_trip, "parenttype": "Dispatch Trip"},
        pluck="transport_request",
        order_by="idx asc",
    )


def _manifest_request_names(dispatch_trip, transport_request=None):
    if not transport_request:
        transport_request = frappe.db.get_value(
            "Dispatch Trip", dispatch_trip, "transport_request"
        )
    return list(
        dict.fromkeys(
            request
            for request in [transport_request, *_assigned_request_names(dispatch_trip)]
            if request
        )
    )


def _manifest_employees(dispatch_trip, transport_request=None):
    seen = set()
    ordered = []
    for request in _manifest_request_names(dispatch_trip, transport_request):
        for employee in _request_workers(request):
            if employee and employee not in seen:
                seen.add(employee)
                ordered.append(employee)
    return ordered


def _manifest_employees_for_stop(dispatch_trip, route_stop):
    stop = frappe.db.get_value(
        "Route Stop",
        route_stop,
        ["stop_name", "accommodation_building"],
        as_dict=True,
    )
    requests = _manifest_request_names(dispatch_trip)
    if not stop or not requests:
        return []

    request_buildings = {
        row.name: row.accommodation_building
        for row in frappe.get_all(
            "Transport Request",
            filters={"name": ["in", requests]},
            fields=["name", "accommodation_building"],
        )
    }
    rows = frappe.get_all(
        "Transport Request Worker",
        filters={"parent": ["in", requests], "parenttype": "Transport Request"},
        fields=["parent", "employee", "pickup_point"],
        order_by="parent asc, idx asc",
    )
    return list(
        dict.fromkeys(
            row.employee
            for row in rows
            if row.employee
            and (
                (row.pickup_point and row.pickup_point == stop.stop_name)
                or (
                    stop.accommodation_building
                    and request_buildings.get(row.parent) == stop.accommodation_building
                )
            )
        )
    )


def ensure_trip_boarding_state(dispatch_trip, transport_request=None, audience=DRIVER):
    if not dispatch_trip:
        return 0
    employees = [e for e in _manifest_employees(dispatch_trip, transport_request) if e]
    if not employees:
        return 0
    trip = frappe.get_doc("Dispatch Trip", dispatch_trip, for_update=True)
    existing = {r.employee for r in (trip.boarding_state or [])}
    added = 0
    for employee in employees:
        if employee in existing:
            continue
        trip.append(
            "boarding_state",
            {"employee": employee, "status": "Pending", "notify_count": 0, "wait_count": 0},
        )
        added += 1
    if added:
        with as_capacity(audience):
            trip.save()
    return added


def mark_boarded(dispatch_trip, employee, source="Scan", audience=DRIVER):
    if not (dispatch_trip and employee):
        return
    trip = frappe.get_doc("Dispatch Trip", dispatch_trip, for_update=True)
    changed = False
    for row in trip.boarding_state or []:
        if row.employee == employee and row.status != "Boarded":
            row.status = "Boarded"
            row.confirm_source = source
            changed = True
    if changed:
        with as_capacity(audience):
            trip.save()
        frappe.cache.delete_value(_MISBOARD_CACHE_PREFIX + employee)


def _driver_contact(dispatch_trip):
    driver = frappe.db.get_value("Dispatch Trip", dispatch_trip, "driver")
    if not driver:
        return None
    d = frappe.db.get_value("Salis Driver", driver, ["full_name", "phone"], as_dict=True)
    if not d:
        return None
    return {"name": d.get("full_name") or driver, "phone": d.get("phone")}


def build_wrong_bus_result(scanned_trip, worker):
    from apex.salis.api.masar import _worker_today_dispatch_trip

    resolved = _worker_today_dispatch_trip(worker)
    if not resolved:
        return None
    correct_trip, transport_request, stop_name, building = resolved
    if correct_trip == scanned_trip:
        return None

    correct_driver = _driver_contact(correct_trip)
    route_plan = frappe.db.get_value("Dispatch Trip", correct_trip, "route_plan")
    result = {
        "wrong_bus": True,
        "correct_trip": correct_trip,
        "correct_driver": correct_driver,
        "route": route_plan,
        "transport_request": transport_request,
    }
    frappe.cache.set_value(
        _MISBOARD_CACHE_PREFIX + worker,
        {
            "scanned_trip": scanned_trip,
            "correct_trip": correct_trip,
            "correct_driver": correct_driver,
            "route": route_plan,
            "at": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
        },
        expires_in_sec=_MISBOARD_TTL_SECONDS,
    )
    return result


def _worker_pickup_arrival(window):
    if not (window and window.get("arrived")):
        return None
    return {"arrived": True, "arrived_at": window.get("arrived_at")}


def _grace_elapsed(dispatch_trip):
    start = frappe.db.get_value(
        "Trip Start Log",
        {"dispatch_trip": dispatch_trip, "docstatus": 0},
        "start_datetime",
    )
    if not start:
        return False
    grace = get_boarding_setting("boarding_grace_minutes")
    return time_diff_in_seconds(now_datetime(), start) >= grace * 60


def _resolve_trip_for_driver(dispatch_trip, ptype="read"):
    return boarding._resolve_trip(dispatch_trip, ptype)


def _state_payload(row, window_seconds):
    return {
        "employee": row.employee,
        "status": row.status,
        "confirm_source": row.confirm_source or None,
        "notify_count": cint(row.notify_count),
        "notify_at": frappe.utils.cstr(row.notify_at) if row.notify_at else None,
        "notify_window_seconds": window_seconds,
        "worker_claim_at": frappe.utils.cstr(row.worker_claim_at) if row.worker_claim_at else None,
        "reject_count": cint(row.reject_count),
        "wait_count": cint(row.wait_count),
        "wait_at": frappe.utils.cstr(row.wait_at) if row.wait_at else None,
    }


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def get_trip_boarding(dispatch_trip):
    _resolve_trip_for_driver(dispatch_trip)

    notify_window = get_boarding_setting("boarding_notify_window_seconds")

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip, for_update=True)

    return {
        "dispatch_trip": dispatch_trip,
        "notify_max_count": get_boarding_setting("boarding_notify_max_count"),
        "notify_window_seconds": notify_window,
        "grace_elapsed": _grace_elapsed(dispatch_trip),
        "worker_wait_request_max": get_boarding_setting("worker_wait_request_max"),
        "worker_wait_request_seconds": get_boarding_setting("worker_wait_request_seconds"),
        "workers": [_state_payload(r, notify_window) for r in (trip.boarding_state or [])],
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def notify_remaining_passengers(dispatch_trip):
    _resolve_trip_for_driver(dispatch_trip, "write")

    max_count = get_boarding_setting("boarding_notify_max_count")
    window = get_boarding_setting("boarding_notify_window_seconds")
    grace_ok = _grace_elapsed(dispatch_trip)

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip, for_update=True)
    now = now_datetime()
    changed = False
    pending_employees = []
    for row in trip.boarding_state or []:
        if row.status != "Pending":
            continue
        pending_employees.append(row.employee)
        row.notify_at = now
        if grace_ok and cint(row.notify_count) < max_count:
            row.notify_count = cint(row.notify_count) + 1
        changed = True
    if changed:
        with as_capacity(DRIVER):
            trip.save()

    _publish(
        "boarding_update",
        dispatch_trip,
        {"max_count": max_count, "window": window},
        driver=trip.driver,
        employees=pending_employees,
    )

    return {
        "dispatch_trip": dispatch_trip,
        "notify_max_count": max_count,
        "notify_window_seconds": window,
        "grace_elapsed": grace_ok,
        "worker_wait_request_max": get_boarding_setting("worker_wait_request_max"),
        "worker_wait_request_seconds": get_boarding_setting("worker_wait_request_seconds"),
        "workers": [_state_payload(r, window) for r in (trip.boarding_state or [])],
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def worker_request_wait(token=None):
    from apex.salis.api.masar import _resolve_worker, _worker_today_dispatch_trip

    employee = _resolve_worker(token)
    resolved = _worker_today_dispatch_trip(employee)
    if not resolved:
        return {"trip": None, "wait_count": 0, "remaining": 0}
    dispatch_trip = resolved[0]

    max_count = get_boarding_setting("worker_wait_request_max")
    window = get_boarding_setting("worker_wait_request_seconds")

    ensure_trip_boarding_state(dispatch_trip, audience=WORKER)
    trip = frappe.get_doc("Dispatch Trip", dispatch_trip, for_update=True)
    target = next((r for r in (trip.boarding_state or []) if r.employee == employee), None)
    if target is None:
        return {"trip": dispatch_trip, "wait_count": 0, "remaining": max_count}

    if cint(target.wait_count) < max_count:
        target.wait_count = cint(target.wait_count) + 1
    target.wait_at = now_datetime()
    with as_capacity(WORKER):
        trip.save()

    wait_count = cint(target.wait_count)
    _publish(
        "wait_request",
        dispatch_trip,
        {
            "employee": employee,
            "wait_count": wait_count,
            "wait_window_seconds": window,
        },
        driver=trip.driver,
        employee=employee,
    )
    return {
        "dispatch_trip": dispatch_trip,
        "wait_count": wait_count,
        "wait_max": max_count,
        "remaining": max(max_count - wait_count, 0),
        "wait_window_seconds": window,
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def worker_claim_boarded(token=None):
    from apex.salis.api.masar import (
        already_boarded,
        get_or_create_trip_log,
        _resolve_worker,
        _worker_today_dispatch_trip,
    )

    employee = _resolve_worker(token)
    resolved = _worker_today_dispatch_trip(employee)
    if not resolved:
        return {"dispatch_trip": None, "status": None}
    dispatch_trip, request_name, stop_name, building = resolved

    window = boarding_window.resolve(dispatch_trip, request_name, building)
    boarding_window.validate_window_is_open(window)

    frappe.db.get_value("Dispatch Trip", dispatch_trip, "name", for_update=True)

    ensure_trip_boarding_state(dispatch_trip, audience=WORKER)
    trip = frappe.get_doc("Dispatch Trip", dispatch_trip, for_update=True)
    target = next((r for r in (trip.boarding_state or []) if r.employee == employee), None)
    if target is None:
        return {"dispatch_trip": dispatch_trip, "status": None}

    log = get_or_create_trip_log(dispatch_trip, employee)
    if not already_boarded(log, employee):
        log.append(
            "boarding_events",
            {
                "worker": employee,
                "stop_name": stop_name,
                "accommodation_building": building,
                "boarded_at": now_datetime(),
                "method": "Worker",
            },
        )
        with as_capacity(WORKER, employee):
            log.save()

    if target.status != "Boarded":
        target.worker_claim_at = now_datetime()
        with as_capacity(WORKER):
            trip.save()
    mark_boarded(dispatch_trip, employee, source="Worker", audience=WORKER)

    _publish(
        "boarding_confirmed",
        dispatch_trip,
        {"employee": employee, "confirm_source": "Worker"},
        driver=trip.driver,
        employee=employee,
    )
    return {
        "dispatch_trip": dispatch_trip,
        "status": "Boarded",
        "confirm_source": "Worker",
        "reject_count": cint(target.reject_count),
        "boarding_window": window,
    }


def _remove_boarding_event(dispatch_trip, employee, driver=None):
    log_name = frappe.db.get_value(
        "Trip Start Log", {"dispatch_trip": dispatch_trip, "docstatus": 0}, "name"
    )
    if not log_name:
        return
    log = frappe.get_doc("Trip Start Log", log_name)
    kept = [
        row for row in (log.boarding_events or [])
        if not (row.worker == employee and not row.is_unregistered)
    ]
    if len(kept) == len(log.boarding_events or []):
        return
    log.set("boarding_events", kept)
    with as_capacity(DRIVER, driver):
        log.save()


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def driver_mark_not_boarded(dispatch_trip, employee):
    _resolve_trip_for_driver(dispatch_trip, "write")

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip, for_update=True)
    target = next((r for r in (trip.boarding_state or []) if r.employee == employee), None)
    if target is None:
        frappe.throw(_("Worker {0} is not on this trip's boarding state.").format(employee))

    _remove_boarding_event(dispatch_trip, employee, trip.driver)

    target.status = "Pending"
    target.confirm_source = None
    target.worker_claim_at = None
    target.reject_count = cint(target.reject_count) + 1
    with as_capacity(DRIVER):
        trip.save()
    _publish(
        "boarding_unmarked",
        dispatch_trip,
        {"employee": employee, "reject_count": cint(target.reject_count)},
        driver=trip.driver,
        employee=employee,
    )

    return {
        "dispatch_trip": dispatch_trip,
        "employee": employee,
        "status": target.status,
        "reject_count": cint(target.reject_count),
    }


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def worker_trip_boarding(token=None):
    from apex.salis.api.masar import _resolve_worker, _worker_today_dispatch_trip

    employee = _resolve_worker(token)
    notify_window_seconds = get_boarding_setting("boarding_notify_window_seconds")
    wait_max = get_boarding_setting("worker_wait_request_max")
    poll_seconds = get_boarding_setting("boarding_active_poll_seconds")
    misboard = frappe.cache.get_value(_MISBOARD_CACHE_PREFIX + employee) if employee else None

    resolved = _worker_today_dispatch_trip(employee)
    if not resolved:
        return {
            "trip": None,
            "poll_seconds": poll_seconds,
            "wrong_bus": misboard or None,
            "boarding_window": boarding_window.resolve(None),
        }
    dispatch_trip = resolved[0]
    building = resolved[3]
    window = boarding_window.resolve(dispatch_trip, resolved[1], building)

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip, for_update=True)
    row = next((r for r in (trip.boarding_state or []) if r.employee == employee), None)
    state = (
        _state_payload(row, notify_window_seconds)
        if row is not None
        else {
            "employee": employee,
            "status": "Pending",
            "notify_count": 0,
            "notify_at": None,
            "notify_window_seconds": notify_window_seconds,
            "wait_count": 0,
            "wait_at": None,
        }
    )
    state.update(
        {
            "dispatch_trip": dispatch_trip,
            "wait_max": wait_max,
            "wait_window_seconds": get_boarding_setting("worker_wait_request_seconds"),
            "poll_seconds": poll_seconds,
            "wrong_bus": misboard or None,
            "driver_arrived": _worker_pickup_arrival(window),
            "boarding_window": window,
        }
    )
    return state


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def depart_and_finalize(dispatch_trip):
    _resolve_trip_for_driver(dispatch_trip, "write")

    max_count = get_boarding_setting("boarding_notify_max_count")
    grace_ok = _grace_elapsed(dispatch_trip)

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip, for_update=True)
    changed = False
    boarded = absent = pending = 0
    for row in trip.boarding_state or []:
        if row.status == "Boarded":
            boarded += 1
            continue
        if row.status == "Absent":
            absent += 1
            continue
        if grace_ok and cint(row.notify_count) >= max_count:
            row.status = "Absent"
            absent += 1
            changed = True
        else:
            pending += 1
    if changed:
        with as_capacity(DRIVER):
            trip.save()

    _close_trip_log(dispatch_trip, trip.driver)

    try:
        from apex.salis.boarding_engine import post_trip_boarding

        post_trip_boarding(dispatch_trip)
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Trip boarding ledger post failed for {dispatch_trip}"[:140],
        )

    _publish(
        "boarding_update",
        dispatch_trip,
        {"finalized": True, "boarded": boarded, "absent": absent},
        driver=trip.driver,
    )
    return {
        "dispatch_trip": dispatch_trip,
        "boarded": boarded,
        "absent": absent,
        "pending": pending,
        "grace_elapsed": grace_ok,
    }


def _close_trip_log(dispatch_trip, driver=None):
    name = frappe.db.get_value(
        "Trip Start Log", {"dispatch_trip": dispatch_trip, "docstatus": 0}, "name"
    )
    if not name:
        return
    log = frappe.get_doc("Trip Start Log", name)
    log.status = "Completed"
    if not log.end_datetime:
        log.end_datetime = now_datetime()
    with as_capacity(DRIVER, driver):
        log.save()
