# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from datetime import datetime, time, timedelta

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, cstr, get_time, getdate, now_datetime

from apex.apex_core.doctype.salis_settings.salis_settings import get_boarding_setting

FINISHED_TRIP_STATUSES = frozenset({"Completed", "Cancelled"})
CLOSED_LOG_STATUSES = frozenset({"Completed", "Cancelled"})
STARTED_TRIP_STATUSES = frozenset({"Dispatched"})

SCHEDULED = "scheduled"
EN_ROUTE = "en_route"
AT_STOP = "at_stop"
DEPARTED = "departed"
FINISHED = "finished"


class BoardingWindowClosed(frappe.ValidationError):
    pass


class BoardingNotOpenYet(BoardingWindowClosed):
    pass


class BoardingStopDeparted(BoardingWindowClosed):
    pass


class BoardingTripFinished(BoardingWindowClosed):
    pass


_REFUSALS = {
    SCHEDULED: (BoardingNotOpenYet, "window_not_open"),
    EN_ROUTE: (BoardingNotOpenYet, "window_not_open"),
    DEPARTED: (BoardingStopDeparted, "stop_departed"),
    FINISHED: (BoardingTripFinished, "trip_finished"),
}


def _refusal_message(state):
    if state == DEPARTED:
        return _("This bus has already left your stop. Ask for a pickup instead of confirming.")
    if state == FINISHED:
        return _("This trip is already finished. Boarding can no longer be confirmed.")
    return _("Your bus has not reached your stop yet. Confirm boarding once it arrives.")


def _seconds_of_day(value):
    if value in (None, ""):
        return None
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    try:
        parsed = get_time(value)
    except Exception:
        return None
    return parsed.hour * 3600 + parsed.minute * 60 + parsed.second


_OWN_STOP_FIELDS = ["name", "idx", "stop_name", "planned_time"]


def _own_stop(dispatch_trip, transport_request, building):
    if not (dispatch_trip and building):
        return None
    stop = frappe.db.get_value(
        "Route Stop",
        {
            "parent": dispatch_trip,
            "parenttype": "Dispatch Trip",
            "accommodation_building": building,
        },
        _OWN_STOP_FIELDS,
        as_dict=True,
    )
    if stop:
        return stop

    route_plan = frappe.db.get_value("Dispatch Trip", dispatch_trip, "route_plan")
    if not route_plan and transport_request:
        route_plan = frappe.db.get_value("Transport Request", transport_request, "route_plan")
    if not route_plan:
        return None
    return frappe.db.get_value(
        "Route Stop",
        {
            "parent": route_plan,
            "parenttype": "Route Plan",
            "accommodation_building": building,
        },
        _OWN_STOP_FIELDS,
        as_dict=True,
    )


def _open_log(dispatch_trip):
    if not dispatch_trip:
        return None
    return frappe.db.get_value(
        "Trip Start Log",
        {"dispatch_trip": dispatch_trip, "docstatus": 0},
        ["name", "status"],
        as_dict=True,
    )


def _progress_rows(log):
    if not log:
        return []
    return frappe.get_all(
        "Trip Stop Progress",
        filters={"parent": log.get("name"), "parenttype": "Trip Start Log"},
        fields=["route_stop", "sequence", "arrived", "arrived_at", "done", "done_at"],
    )


def _bus_is_past(rows, own_stop):
    if not own_stop:
        return False
    own_sequence = cint(own_stop.get("idx"))
    if not own_sequence:
        return False
    return any(
        cint(row.get("sequence")) > own_sequence and (row.get("arrived") or row.get("done"))
        for row in rows
    )


def _window_anchor(trip, own_stop):
    trip_date = trip.get("trip_date")
    if not trip_date:
        return None
    candidates = [
        seconds
        for seconds in (
            _seconds_of_day(own_stop.get("planned_time")) if own_stop else None,
            _seconds_of_day(trip.get("depart_time")),
        )
        if seconds is not None
    ]
    if not candidates:
        return None
    return datetime.combine(getdate(trip_date), time.min) + timedelta(seconds=min(candidates))


def resolve(dispatch_trip, transport_request=None, building=None, now=None):
    now = now or now_datetime()
    trip = (
        frappe.db.get_value(
            "Dispatch Trip", dispatch_trip, ["status", "trip_date", "depart_time"], as_dict=True
        )
        if dispatch_trip
        else None
    ) or {}

    own_stop = _own_stop(dispatch_trip, transport_request, building)
    log = _open_log(dispatch_trip)
    rows = _progress_rows(log)
    mine = next(
        (r for r in rows if own_stop and r.get("route_stop") == own_stop.get("name")), None
    )
    anchor = _window_anchor(trip, own_stop)
    grace = get_boarding_setting("boarding_grace_minutes")
    opens_at = add_to_date(anchor, minutes=-grace) if anchor else None

    if not dispatch_trip:
        state = SCHEDULED
    elif trip.get("status") in FINISHED_TRIP_STATUSES:
        state = FINISHED
    elif mine and mine.get("done"):
        state = DEPARTED
    elif log and log.get("status") in CLOSED_LOG_STATUSES:
        state = DEPARTED
    elif _bus_is_past(rows, own_stop):
        state = DEPARTED
    elif mine and mine.get("arrived"):
        state = AT_STOP
    elif opens_at is None or now >= opens_at:
        state = AT_STOP
    elif log or trip.get("status") in STARTED_TRIP_STATUSES:
        state = EN_ROUTE
    else:
        state = SCHEDULED

    window = {
        "dispatch_trip": dispatch_trip or None,
        "state": state,
        "can_confirm": state == AT_STOP,
        "reason": _REFUSALS[state][1] if state in _REFUSALS else None,
        "stop_name": own_stop.get("stop_name") if own_stop else None,
        "grace_minutes": grace,
        "anchor_at": cstr(anchor) if anchor else None,
        "opens_at": cstr(opens_at) if opens_at else None,
        "arrived": bool(mine and mine.get("arrived")),
        "arrived_at": cstr(mine.get("arrived_at")) if mine and mine.get("arrived_at") else None,
        "done_at": cstr(mine.get("done_at")) if mine and mine.get("done_at") else None,
    }
    return window


def validate_window_is_open(window):
    if window.get("can_confirm"):
        return
    exc = _REFUSALS.get(window.get("state"), (BoardingWindowClosed, None))[0]
    frappe.throw(_refusal_message(window.get("state")), exc=exc)
