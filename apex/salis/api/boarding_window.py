# Copyright (c) 2026, afmcoltd
"""The worker's boarding window — when a self-confirm is evidence, and when it is a lie.

A worker tapping "I'm on the bus" is only evidence if the bus is at HIS stop when he
taps. Scoping that to the calendar day is not enough: a 07:00 trip stays confirmable
at 23:00, and a bus that has already served his stop still accepts him, so the gate
manifest reports a headcount that includes a man standing at the camp.

The window is tied to ONE stop — the worker's own pickup, the Route Stop whose
``accommodation_building`` is the building his transport request collects him from —
and that stop moves through five states:

``scheduled``  the trip has not started; there is nothing to board.
``en_route``   the driver has started but has not reached this worker's stop.
``at_stop``    the window is OPEN. This is the only state a self-confirm is accepted in.
``departed``   the driver marked this stop done, marked a LATER stop, or closed the
               trip's manifest. The bus has gone, and a confirm now is the lie the
               gate manifest would read as a headcount.
``finished``   the trip itself is Completed or Cancelled.

It opens at the EARLIER of the driver's recorded arrival at that stop and
``boarding_grace_minutes`` before the stop's planned time, and closes when the driver
marks that stop done. Both ends read Trip Stop Progress — the per-stop rail the driver
portal already writes through ``mark_arrived`` and ``mark_stop_progress`` — and every
threshold is read from Salis Settings. The clock only ever OPENS the window; every one
of its closes is something a driver recorded.

MISSING EVIDENCE OPENS THE WINDOW; IT NEVER CLOSES IT. A driver who forgets to tap
arrival, a trip whose stop progress was never written, a route with no per-stop
planned time and a trip with no departure time: each of those falls through to the
time branch or straight to ``at_stop`` rather than refusing. A refusal that is wrong
strands a real worker at a real stop with no way to be counted, while a confirm that
is wrong is already reversible through the driver's ``driver_mark_not_boarded``
override. That asymmetry is the whole reason the gate leans open.
"""

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
    """A boarding self-confirm that landed outside the worker's own stop window."""


class BoardingNotOpenYet(BoardingWindowClosed):
    """The bus has not reached the worker's stop yet."""


class BoardingStopDeparted(BoardingWindowClosed):
    """The bus has already served the worker's stop and moved on."""


class BoardingTripFinished(BoardingWindowClosed):
    """The trip itself is over."""


_REFUSALS = {
    SCHEDULED: (BoardingNotOpenYet, "window_not_open"),
    EN_ROUTE: (BoardingNotOpenYet, "window_not_open"),
    DEPARTED: (BoardingStopDeparted, "stop_departed"),
    FINISHED: (BoardingTripFinished, "trip_finished"),
}


def _refusal_message(state):
    """The worker-facing sentence for a refused self-confirm, naming which end of the
    window it fell outside of."""
    if state == DEPARTED:
        return _("This bus has already left your stop. Ask for a pickup instead of confirming.")
    if state == FINISHED:
        return _("This trip is already finished. Boarding can no longer be confirmed.")
    return _("Your bus has not reached your stop yet. Confirm boarding once it arrives.")


def _seconds_of_day(value):
    """A Time field as seconds since midnight, or None when it carries no time.

    Frappe hands a Time column back as a ``datetime.timedelta``, which is already the
    offset from midnight; anything else is parsed."""
    if value in (None, ""):
        return None
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    try:
        parsed = get_time(value)
    except Exception:
        return None
    return parsed.hour * 3600 + parsed.minute * 60 + parsed.second


def _own_stop(dispatch_trip, transport_request, building):
    """The worker's OWN Route Stop on this trip: its stable row name (the key the
    driver's Trip Stop Progress rows are written against), its position on the route
    and its planned time.

    None when the trip has no route plan, the worker has no pickup building, or the
    plan carries no stop for that building — every one of which leaves the caller
    unable to identify his stop, and therefore unable to refuse him."""
    if not (dispatch_trip and building):
        return None
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
        ["name", "idx", "stop_name", "planned_time"],
        as_dict=True,
    )


def _open_log(dispatch_trip):
    """The trip's open (draft) Trip Start Log with its status — the record the driver's
    per-stop progress hangs off, and the one ``depart_and_finalize`` closes."""
    if not dispatch_trip:
        return None
    return frappe.db.get_value(
        "Trip Start Log",
        {"dispatch_trip": dispatch_trip, "docstatus": 0},
        ["name", "status"],
        as_dict=True,
    )


def _progress_rows(log):
    """Every Trip Stop Progress row on the trip's open log. One read serves both
    questions the window asks: what the driver recorded at THIS worker's stop, and
    whether he has recorded anything at a stop further down the route."""
    if not log:
        return []
    return frappe.get_all(
        "Trip Stop Progress",
        filters={"parent": log.get("name"), "parenttype": "Trip Start Log"},
        fields=["route_stop", "sequence", "arrived", "arrived_at", "done", "done_at"],
    )


def _bus_is_past(rows, own_stop):
    """True when the driver has marked a stop LATER on the route than this worker's.

    The bus cannot be at stop three and still at stop one, so a later mark is
    recorded proof that this worker's stop is behind it — the case the per-stop
    ``done`` flag misses when a driver marks arrival onward but never closes the
    stop he left. An earlier stop's mark says nothing and is ignored."""
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
    """The instant the window opens from, before the grace is taken off it."""
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
    """The worker's boarding-window state on one trip, as one of the five states.

    ``building`` is the worker's own pickup building — the axis the whole window turns
    on. Without a dispatch trip there is nothing to board and the answer is
    ``scheduled``. Without an identifiable stop the trip's own departure governs and
    no per-stop mark can close anything, so a worker whose stop the data cannot name
    is never shut out by a mark that was not about him.

    Returns a JSON-safe dict the SPAs render directly: the ``state``, whether a
    self-confirm is accepted (``can_confirm``), the machine ``reason`` it is not, the
    stop it is about, and the timestamps behind the verdict."""
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
        "eta_minutes": None,
    }
    if state == EN_ROUTE:
        from apex.salis.api.masar import compute_ride_eta_minutes

        window["eta_minutes"] = compute_ride_eta_minutes(dispatch_trip, building)
    return window


def refuse_unless_open(window):
    """Refuse a boarding self-confirm outside the window, naming WHY.

    Raises the state's own exception class, so the caller — and the SPA, which reads
    the thrown ``exc_type`` — gets the reason rather than a bare failure. A no-op
    while the window is open, so a write path guards itself with one line before it
    touches the manifest log."""
    if window.get("can_confirm"):
        return
    exc = _REFUSALS.get(window.get("state"), (BoardingWindowClosed, None))[0]
    frappe.throw(_refusal_message(window.get("state")), exc=exc)
