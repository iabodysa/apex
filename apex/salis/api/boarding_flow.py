# Copyright (c) 2026, afmcoltd
"""Salis boarding/departure flow — driver "remaining passengers" notify, worker
"please wait" request + self-confirm boarding, the worker boarding poll, and the
depart/finalize close.

Worker self-confirm model: a worker's "I'm on the bus" claim self-confirms
(records the boarding event + marks them Boarded) and NOTIFIES the driver; there
is no per-worker driver-approval gate. The driver intervenes only for an
exception — driver_mark_not_boarded reverses a self-confirm (wrong bus / mistaken
tap). ``worker_claim_at`` still stamps the moment of that claim and feeds the ledger's
``boarded_at``; what is gone is the auto-confirm timeout that once flipped a separate
"Worker Claimed" state, because self-confirm made that state unreachable.

Builds on the existing boarding pass + manifest (``salis/api/boarding.py``) and
the worker token identity (``salis/api/masar.py``); it does NOT duplicate the
manifest or the Trip Start Log. The per-worker flow state lives in the
``Trip Boarding State`` child table on Dispatch Trip, populated from the trip's
manifest the first time the trip starts (the first scan / self-confirm).

Realtime rides the shared channel pattern: ``frappe.publish_realtime`` with
``doctype="Dispatch Trip"`` and ``after_commit=True`` (the socket server gates
delivery on read permission; the SPA treats the payload as advisory and refetches).

No GL, no money. The driver phone is operational — returned only to the scanning
driver and the affected worker, and never logged.

The flow-state writes here no longer bypass permissions. Each one runs inside ``as_capacity`` —
the token authenticates, the capacity user carries the role — and Dispatch Trip holds the wall
that makes that safe: every field except ``boarding_state`` sits at ``permlevel 1``, so a rider
writes their own row and the route, vehicle and driver assignment stay out of reach. The framework
RESETS an unauthorised field rather than refusing the save (``document.py:795``), which is why
that guarantee is asserted on the value after the save rather than on an exception.

The ``Trip Start Log`` writes run inside ``as_capacity`` too, bound to the identity each caller
already resolved (the driver for the two driver-authored writes below, the worker for the
self-confirm) — ``apex.salis.permissions._trip_start_log_capacity_verdict`` is what refuses one
holder's write against another's log, not a DocPerm on the shared capacity role alone.
"""

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
from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.apex_core.doctype.salis_settings.salis_settings import (
    get_boarding_setting,
)
from apex.salis.api import boarding_window


_MISBOARD_CACHE_PREFIX = "salis_misboard:"
_MISBOARD_TTL_SECONDS = 30 * 60


def _publish(event, dispatch_trip, payload, driver=None, employee=None, employees=None):
    """Announce a boarding flow event to everyone entitled to hear it.

    The Dispatch Trip room reaches DESK subscribers, who hold read permission on it.
    It can never reach a portal: /driver and /masar are Guest sessions carrying a
    token, and frappe's socket server gates a doctype room on read permission, so a
    publish routed only there is emitted and never delivered. The portal subjects are
    therefore rung on their own rooms as well — see
    ``portal_identity.portal_room``.

    after_commit so subscribers read committed state; best-effort so a publish
    failure can never abort the calling write."""
    body = {"dispatch_trip": dispatch_trip, **payload}
    try:
        frappe.publish_realtime(
            event,
            body,
            doctype="Dispatch Trip",
            after_commit=True,
        )
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
        from apex.salis.api.web_push import enqueue_boarding_event

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
    """Ordered Employee ids on one Transport Request's worker manifest."""
    if not transport_request:
        return []
    return frappe.get_all(
        "Transport Request Worker",
        filters={"parent": transport_request, "parenttype": "Transport Request"},
        pluck="employee",
        order_by="idx asc",
    )


def _assigned_request_names(dispatch_trip):
    """The Transport Requests assigned onto the trip (the supervisor assignment)."""
    if not dispatch_trip:
        return []
    return frappe.get_all(
        "Dispatch Trip Assigned Request",
        filters={"parent": dispatch_trip, "parenttype": "Dispatch Trip"},
        pluck="transport_request",
        order_by="idx asc",
    )


def _manifest_request_names(dispatch_trip, transport_request=None):
    """Ordered Transport Requests that contribute workers to one trip."""
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
    """The trip's expected manifest: the de-duplicated UNION of the Route Plan
    Transport Request's workers and every assigned-request's workers, preserving
    first-seen order. The Route Plan path and the supervisor assignment path are
    additive — a trip can carry either or both."""
    seen = set()
    ordered = []
    for request in _manifest_request_names(dispatch_trip, transport_request):
        for employee in _request_workers(request):
            if employee and employee not in seen:
                seen.add(employee)
                ordered.append(employee)
    return ordered


def _manifest_employees_for_stop(dispatch_trip, route_stop):
    """Workers whose request pickup matches one route stop."""
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
    """Populate Dispatch Trip's boarding_state from the manifest, once per trip.

    Called from the trip-start path (the first scan / self-confirm get-or-create
    of the Trip Start Log), so the per-worker state exists the moment a trip
    begins. Idempotent: it only adds rows for manifest workers not already
    present, so a later manifest growth is picked up and re-running never
    duplicates a worker. Writes directly to the (possibly submitted) Dispatch
    Trip via db_set on the child table — the field is allow_on_submit and the
    caller already authorised the trip. Returns the number of rows added."""
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
    """Flip a worker's boarding state to Boarded (idempotent). Called from the
    boarding paths when a worker's boarding event is recorded, so the flow state
    tracks the manifest. ``source`` records HOW (Scan for a QR scan, Manual for a
    driver entry). Best-effort: a missing row (e.g. an unregistered rider) is
    simply skipped."""
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
    """The driver's display name + operational phone for a trip, or None. The
    phone is returned only to the scanning driver and the affected worker."""
    driver = frappe.db.get_value("Dispatch Trip", dispatch_trip, "driver")
    if not driver:
        return None
    d = frappe.db.get_value("Salis Driver", driver, ["full_name", "phone"], as_dict=True)
    if not d:
        return None
    return {"name": d.get("full_name") or driver, "phone": d.get("phone")}


def build_wrong_bus_result(scanned_trip, worker):
    """Resolve the worker's REAL trip today (+ its driver + route) when they
    scanned onto the wrong bus, and record a transient misboard hint their poll
    can read. Returns the structured correction, or None when no real trip is
    found (the caller then falls back to the plain Wrong Trip result).

    Resolved forward from today's trips via the worker's own manifest membership
    (the same direction masar._worker_today_dispatch_trip uses), so it can only
    ever reach a trip the worker is actually on."""
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
    """The "driver has arrived at your pickup" state for the worker, or None.

    Reads the arrival off the already-resolved boarding window rather than
    re-deriving it: ``boarding_window`` resolves the worker's own Route Stop from his
    pickup building and reads the driver's ``arrived`` flag on that stop's Trip Stop
    Progress row, which is the same join this signal has always used. Returns
    ``{"arrived": True, "arrived_at": ...}`` only once the driver has marked arrival
    at that stop; otherwise None (the client shows nothing). Read-only — a guest
    worker has no socket, so the poll is the delivery path for this signal."""
    if not (window and window.get("arrived")):
        return None
    return {"arrived": True, "arrived_at": window.get("arrived_at")}


def _grace_elapsed(dispatch_trip):
    """True once boarding_grace_minutes have passed since the trip started. Before
    that, escalation/absence is suppressed (workers are still arriving). With no
    start log yet, grace is treated as NOT elapsed (the trip has not begun)."""
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
    """Resolve credential-first caller scope before reading the trip.

    A presented driver credential is confined to its own trip. Staff and linked
    driver session fallbacks are considered only without a driver credential.

    ``ptype`` names the right the endpoint below is about to exercise, and is what
    confines a project-scoped staff caller to their own project's trips — see
    ``boarding._resolve_trip``. An endpoint that mutates the trip MUST pass
    "write"; the default suits the manifest reads only.
    """
    from apex.salis.api import boarding

    return boarding._resolve_trip(dispatch_trip, ptype)


def _state_payload(row, window_seconds):
    """A single Trip Boarding State row as a JSON-safe dict (shared shape)."""
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
    """Driver panel read: the trip's full boarding state (READ, no side effects).

    The notify action bumps notify_count after grace, so the driver panel must
    NOT open by calling it — merely viewing the manifest would burn a reminder on
    every Pending worker. This endpoint is the pure read: it writes nothing to
    notify_count / notify_at and publishes no event. It DOES settle any timed-out
    worker claims (the auto-confirm timeout, same as the worker poll), so the
    driver sees auto-confirmed rows; that flip is a system timeout the read merely
    realises, not a driver side effect on the notify quota.

    Returns the same per-worker shape as notify_remaining_passengers plus the
    worker-wait settings (for the driver's "n of max" wait display). Caller scope
    is resolved credential-first before any trip access."""
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
    """Driver action: nudge every still-Pending worker (write, driver-scoped).

    For each Pending boarding-state row, bump notify_count (capped at
    boarding_notify_max_count) and stamp notify_at=now, then publish a
    ``boarding_update`` to the Dispatch Trip room so the workers' polls pick up
    the new countdown. The escalation only counts once the grace window has
    elapsed (before that the nudge is recorded but the count is not raised, so an
    early tap cannot burn a worker's quota). Returns the per-worker state.

    Caller scope is resolved credential-first before any trip access."""
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
    """Worker action: "please wait, I'm coming" (write, token-scoped).

    Resolves the token to one Employee (the sole identity source — the client
    never supplies a worker id), finds their today's trip from their OWN manifest,
    and bumps that worker's wait_count (capped at worker_wait_request_max) with
    wait_at=now. Publishes a ``wait_request`` to the Dispatch Trip room so the
    driver's socket surfaces it. Returns the new count + remaining.

    A worker with no boardable trip today, or not on the trip's boarding state, is
    a clean no-op. Tight rate_limit so a personal link cannot spam the driver."""
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
    """Worker action: "I'm on board" self-confirm (write, token-scoped).

    The worker's claim SELF-CONFIRMS — there is no per-worker driver-approval gate,
    so the only thing standing between a tap and the gate manifest is the boarding
    window: the claim is accepted only while ``boarding_window`` puts the worker's
    OWN stop in ``at_stop``, and is refused with a named reason — before the trip is
    locked and before any state or log is written — when the bus has not reached that
    stop, has already left it, or the trip is over.

    Resolves the token to one Employee (sole identity source), finds their today's
    trip from their OWN manifest, records the boarding event (the SAME
    ``method=Worker`` Trip Boarding Event + shared get-or-create log
    ``masar.confirm_boarding`` writes, so the manifest headcount reconciles), and
    flips their boarding-state row to ``Boarded`` (confirm_source=Worker,
    worker_claim_at=now for the ledger's boarded_at). Publishes
    ``boarding_confirmed`` so the driver is NOTIFIED (not asked to approve) — the
    driver intervenes only via the exception override (driver_mark_not_boarded).

    Idempotent: an already-Boarded row records no second event and stays Boarded; a
    re-confirm from ``Pending`` (e.g. after a driver "not boarded" override) boards
    again. A worker with no boardable trip today, or not on the trip's boarding
    state, is a clean no-op. Tight rate_limit so a personal link cannot spam.

    Returns ``{"dispatch_trip": str|None, "status": str|None, ...}`` on EVERY path —
    one key name for the trip, so a caller can tell the two no-ops apart instead of
    reading ``undefined``: no boardable trip today is ``dispatch_trip = None``, a
    worker not on that trip's manifest is a REAL ``dispatch_trip`` with
    ``status = None``, and a self-confirm is ``status = "Boarded"`` plus
    ``confirm_source`` and ``reject_count``."""
    from apex.salis.api.masar import (
        already_boarded,
        _get_or_create_trip_log,
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

    log = _get_or_create_trip_log(dispatch_trip, employee)
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
    """Drop a worker's registered boarding event from the trip's open manifest log
    (the driver "not boarded" exception reversing a self-confirm). Best-effort: no
    open log or no row for the worker is a clean no-op. Leaves any unregistered
    rider rows untouched. ``driver`` is the resolved caller of the exception (its sole
    caller, ``driver_mark_not_boarded``, already has it); the write runs inside
    ``as_capacity(DRIVER, driver)``."""
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
    """Driver EXCEPTION override: reverse a worker's self-confirm (write, driver-scoped).

    The per-worker driver-approval gate is gone — a worker's claim self-confirms.
    The driver only intervenes for an exception: a worker who self-confirmed but is
    NOT actually aboard (wrong bus, mistaken tap). This drops their boarding event
    from the manifest log and resets the state row to ``Pending`` (so they can
    re-confirm if they do board), bumping reject_count for the audit. Publishes
    ``boarding_unmarked`` so the worker's poll surfaces it. Caller scope is
    resolved credential-first before any trip access."""
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
    """Worker poll: the worker's current boarding state (read, token-scoped).

    Resolves the token to one Employee and returns their state on today's trip —
    status, the active notify_at + window (for the client countdown),
    wait_count/max, the poll cadence, any wrong_bus correction (the correct trip +
    driver phone) held as a transient hint from a misboarded scan,
    ``driver_arrived`` (the "your driver has arrived at your pickup" signal — set
    once the driver marks arrival at the worker's own pickup stop, else None; the
    guest worker has no socket, so this poll is the delivery path), and
    ``boarding_window`` — the five-state verdict on his own stop, which is what tells
    the screen whether to show a live confirm button, an ETA, or a missed-ride
    request. The driver phone is returned only to the affected worker. Read-only.

    ``{"trip": None}`` with any pending misboard hint when the worker has no
    boardable trip on this bus; a worker not on the trip's boarding state gets a
    Pending default so the client always has a shape to render."""
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
    """Driver action: depart — mark exhausted Pending workers Absent, close the
    manifest (write, driver-scoped).

    Any still-Pending worker whose notify_count has reached
    boarding_notify_max_count is marked Absent; the rest stay as they are. The
    open Trip Start Log is moved to Completed (its end stamped). Absence only
    applies after the grace window has elapsed (an early depart marks no one
    Absent). Publishes a ``boarding_update``. Returns the boarded vs absent
    counts.

    Caller scope is resolved credential-first before any trip access."""
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
    """Move the trip's open draft Trip Start Log to Completed with an end stamp.
    The headcount log is the manifest record; finalize closes it. No-op when no
    open log exists (the trip never had a boarding event). ``driver`` is the resolved
    caller of the sole caller, ``depart_and_finalize``; the write runs inside
    ``as_capacity(DRIVER, driver)``."""
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
