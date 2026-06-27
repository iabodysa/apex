"""Salis boarding/departure flow — driver "remaining passengers" notify, worker
"please wait" request, the worker boarding poll, and the depart/finalize close.

Builds on the existing boarding pass + manifest (``salis/api/boarding.py``) and
the worker token identity (``salis/api/masar.py``); it does NOT duplicate the
manifest or the Trip Start Log. The per-worker flow state lives in the
``Trip Boarding State`` child table on Dispatch Trip, populated from the trip's
manifest the first time the trip starts (the first scan / self-confirm).

Realtime rides the P-032 channel pattern: ``frappe.publish_realtime`` with
``doctype="Dispatch Trip"`` and ``after_commit=True`` (the socket server gates
delivery on read permission; the SPA treats the payload as advisory and refetches).

No GL, no money. The driver phone is operational — returned only to the scanning
driver and the affected worker, and never logged.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, now_datetime, time_diff_in_seconds

from apex_habitat.apex_core.doctype.salis_settings.salis_settings import (
    get_boarding_setting,
)

# Transient cross-request flag a misboarded worker's poll can read: keyed by the
# worker's Employee id, holds the correct trip/driver correction the scan resolved.
# TTL'd in the cache (volatile by design — it is a hint, not a record).
_MISBOARD_CACHE_PREFIX = "salis_misboard:"
_MISBOARD_TTL_SECONDS = 30 * 60


def _publish(event, dispatch_trip, payload):
    """Publish a boarding flow event to the Dispatch Trip room (P-032 pattern).

    after_commit so subscribers read committed state; best-effort so a publish
    failure can never abort the calling write."""
    try:
        frappe.publish_realtime(
            event,
            {"dispatch_trip": dispatch_trip, **payload},
            doctype="Dispatch Trip",
            after_commit=True,
        )
    except Exception:
        pass


# Trip Boarding State — populate from the manifest when the trip starts.


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


def _manifest_employees(dispatch_trip, transport_request=None):
    """The trip's expected manifest: the de-duplicated UNION of the Route Plan
    Transport Request's workers and every assigned-request's workers, preserving
    first-seen order. The Route Plan path and the supervisor assignment path are
    additive — a trip can carry either or both."""
    if not transport_request:
        transport_request = frappe.db.get_value(
            "Dispatch Trip", dispatch_trip, "transport_request"
        )
    seen = set()
    ordered = []
    for request in [transport_request, *_assigned_request_names(dispatch_trip)]:
        for employee in _request_workers(request):
            if employee and employee not in seen:
                seen.add(employee)
                ordered.append(employee)
    return ordered


def ensure_trip_boarding_state(dispatch_trip, transport_request=None):
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
    trip = frappe.get_doc("Dispatch Trip", dispatch_trip)
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
        # trip authorised by the calling boarding path; allow_on_submit field lets a
        # started (submitted) trip still be seeded.
        trip.save(ignore_permissions=True)  # audit-ok
    return added


def mark_boarded(dispatch_trip, employee, source="Scan"):
    """Flip a worker's boarding state to Boarded (idempotent). Called from the
    boarding paths when a worker's boarding event is recorded, so the flow state
    tracks the manifest. ``source`` records HOW (Scan for a QR scan, Manual for a
    driver entry). Best-effort: a missing row (e.g. an unregistered rider) is
    simply skipped."""
    if not (dispatch_trip and employee):
        return
    trip = frappe.get_doc("Dispatch Trip", dispatch_trip)
    changed = False
    for row in trip.boarding_state or []:
        if row.employee == employee and row.status != "Boarded":
            row.status = "Boarded"
            row.confirm_source = source
            changed = True
    if changed:
        trip.save(ignore_permissions=True)  # audit-ok: boarding path authorised the trip
        # Clear any stale misboard hint now that the worker has boarded somewhere.
        frappe.cache.delete_value(_MISBOARD_CACHE_PREFIX + employee)


# Feature A — wrong bus correction (consumed by scan_boarding_pass).


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
    from apex_habitat.salis.api.masar import _worker_today_dispatch_trip

    resolved = _worker_today_dispatch_trip(worker)
    if not resolved:
        return None
    correct_trip, transport_request, stop_name, building = resolved
    if correct_trip == scanned_trip:
        # Already the right trip after all — not a misboard.
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
    # Transient hint the worker's poll surfaces (volatile; a hint, not a record).
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


def _read_misboard(worker):
    """The worker's transient wrong-bus correction hint, or None."""
    if not worker:
        return None
    return frappe.cache.get_value(_MISBOARD_CACHE_PREFIX + worker)


# Grace gate.


def _trip_start_dt(dispatch_trip):
    """The trip's start instant — the open Trip Start Log's start_datetime, falling
    back to None (no log yet means the trip has not really started)."""
    return frappe.db.get_value(
        "Trip Start Log",
        {"dispatch_trip": dispatch_trip, "docstatus": 0},
        "start_datetime",
    )


def _grace_elapsed(dispatch_trip):
    """True once boarding_grace_minutes have passed since the trip started. Before
    that, escalation/absence is suppressed (workers are still arriving). With no
    start log yet, grace is treated as NOT elapsed (the trip has not begun)."""
    start = _trip_start_dt(dispatch_trip)
    if not start:
        return False
    grace = get_boarding_setting("boarding_grace_minutes")
    return time_diff_in_seconds(now_datetime(), start) >= grace * 60


# Two-sided confirmation — auto-confirm the worker claim after the timeout.


def _apply_auto_confirm(trip):
    """In-place: any Worker Claimed row whose claim is older than
    boarding_auto_confirm_minutes becomes Boarded (confirm_source=Auto). Mutates
    the passed Dispatch Trip doc's child rows but does NOT save — the caller
    decides whether to persist. Returns the number of rows flipped.

    This is the robust core of the 1/4-hour rule: it is evaluated at read time
    (worker poll, depart) AND by the scheduled tick, so a claim confirms even
    with no read path."""
    minutes = get_boarding_setting("boarding_auto_confirm_minutes")
    cutoff_seconds = minutes * 60
    now = now_datetime()
    flipped = 0
    for row in trip.boarding_state or []:
        if row.status != "Worker Claimed" or not row.worker_claim_at:
            continue
        if time_diff_in_seconds(now, row.worker_claim_at) >= cutoff_seconds:
            row.status = "Boarded"
            row.confirm_source = "Auto"
            flipped += 1
    return flipped


def auto_confirm_claimed_boardings():
    """Scheduled tick: auto-confirm timed-out worker claims across all active
    trips, independent of any read path. Scans Dispatch Trips that have at least
    one Worker Claimed boarding-state row and applies the timeout to each.

    Registered in hooks scheduler_events (every few minutes). Idempotent and
    cheap: a trip with no eligible claim is left untouched."""
    trips = frappe.get_all(
        "Trip Boarding State",
        filters={"status": "Worker Claimed", "parenttype": "Dispatch Trip"},
        pluck="parent",
        distinct=True,
    )
    confirmed = 0
    for name in set(trips):
        trip = frappe.get_doc("Dispatch Trip", name)
        flipped = _apply_auto_confirm(trip)
        if flipped:
            trip.save(ignore_permissions=True)  # audit-ok: system tick, no user identity
            confirmed += flipped
            _publish("boarding_update", name, {"auto_confirmed": flipped})
    if confirmed:
        frappe.db.commit()
    return confirmed


# Feature B — endpoints.


def _resolve_trip_for_driver(dispatch_trip):
    """Authorise the caller on the trip (own trip for a driver, any for staff) by
    reusing boarding._resolve_trip, and return the trip dict."""
    from apex_habitat.salis.api import boarding

    return boarding._resolve_trip(dispatch_trip)


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


@frappe.whitelist()
@rate_limit(key="frappe.request.remote_addr", limit=120, seconds=60)
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
    worker-wait settings (for the driver's "n of max" wait display). Caller must
    be allowed to act on the trip; resolved server-side."""
    _resolve_trip_for_driver(dispatch_trip)

    notify_window = get_boarding_setting("boarding_notify_window_seconds")

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip)
    # Realise timed-out claims on read (no notify-quota effect); persist only the
    # timeout flip, never a notify bump.
    if _apply_auto_confirm(trip):
        trip.save(ignore_permissions=True)  # audit-ok: system timeout, read-time confirm

    return {
        "dispatch_trip": dispatch_trip,
        "notify_max_count": get_boarding_setting("boarding_notify_max_count"),
        "notify_window_seconds": notify_window,
        "grace_elapsed": _grace_elapsed(dispatch_trip),
        "worker_wait_request_max": get_boarding_setting("worker_wait_request_max"),
        "worker_wait_request_seconds": get_boarding_setting("worker_wait_request_seconds"),
        "workers": [_state_payload(r, notify_window) for r in (trip.boarding_state or [])],
    }


@frappe.whitelist(methods=["POST"])
@rate_limit(key="frappe.request.remote_addr", limit=60, seconds=60)
def notify_remaining_passengers(dispatch_trip):
    """Driver action: nudge every still-Pending worker (write, driver-scoped).

    For each Pending boarding-state row, bump notify_count (capped at
    boarding_notify_max_count) and stamp notify_at=now, then publish a
    ``boarding_update`` to the Dispatch Trip room so the workers' polls pick up
    the new countdown. The escalation only counts once the grace window has
    elapsed (before that the nudge is recorded but the count is not raised, so an
    early tap cannot burn a worker's quota). Returns the per-worker state.

    Caller must be allowed to act on the trip (own trip for a driver, any for
    Salis staff); resolved server-side."""
    _resolve_trip_for_driver(dispatch_trip)

    max_count = get_boarding_setting("boarding_notify_max_count")
    window = get_boarding_setting("boarding_notify_window_seconds")
    grace_ok = _grace_elapsed(dispatch_trip)

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip)
    now = now_datetime()
    changed = False
    for row in trip.boarding_state or []:
        if row.status != "Pending":
            continue
        row.notify_at = now
        # Only consume the quota after grace; before grace the nudge is a soft ping.
        if grace_ok and cint(row.notify_count) < max_count:
            row.notify_count = cint(row.notify_count) + 1
        changed = True
    if changed:
        trip.save(ignore_permissions=True)  # audit-ok: driver authorised on the trip

    _publish("boarding_update", dispatch_trip, {"max_count": max_count, "window": window})

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
    from apex_habitat.salis.api.masar import _resolve_worker, _worker_today_dispatch_trip

    employee = _resolve_worker(token)
    resolved = _worker_today_dispatch_trip(employee)
    if not resolved:
        return {"trip": None, "wait_count": 0, "remaining": 0}
    dispatch_trip = resolved[0]

    max_count = get_boarding_setting("worker_wait_request_max")
    window = get_boarding_setting("worker_wait_request_seconds")

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip)
    target = next((r for r in (trip.boarding_state or []) if r.employee == employee), None)
    if target is None:
        return {"trip": dispatch_trip, "wait_count": 0, "remaining": max_count}

    if cint(target.wait_count) < max_count:
        target.wait_count = cint(target.wait_count) + 1
    target.wait_at = now_datetime()
    trip.save(ignore_permissions=True)  # audit-ok: worker + trip resolved from token

    wait_count = cint(target.wait_count)
    _publish(
        "wait_request",
        dispatch_trip,
        {
            "employee": employee,
            "wait_count": wait_count,
            "wait_window_seconds": window,
        },
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
    """Worker action: "I'm on board" self-claim (write, token-scoped).

    Resolves the token to one Employee (sole identity source), finds their today's
    trip from their OWN manifest, and moves their boarding-state row to
    ``Worker Claimed`` with worker_claim_at=now — starting the auto-confirm clock.
    A re-claim from ``Driver Rejected`` resets the row back to ``Worker Claimed``
    (the worker's "try again / re-assert"); an already-Boarded row is left as is.
    Publishes a ``boarding_claim`` to the Dispatch Trip room so the driver is
    prompted to confirm. Returns the new state.

    A worker with no boardable trip today, or not on the trip's boarding state, is
    a clean no-op. Tight rate_limit so a personal link cannot spam the driver."""
    from apex_habitat.salis.api.masar import _resolve_worker, _worker_today_dispatch_trip

    employee = _resolve_worker(token)
    resolved = _worker_today_dispatch_trip(employee)
    if not resolved:
        return {"trip": None, "status": None}
    dispatch_trip = resolved[0]

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip)
    target = next((r for r in (trip.boarding_state or []) if r.employee == employee), None)
    if target is None:
        return {"trip": dispatch_trip, "status": None}
    if target.status == "Boarded":
        # Already confirmed; a claim does not undo a real boarding.
        return {"dispatch_trip": dispatch_trip, "status": target.status}

    # Pending or Driver Rejected -> (re)assert the claim.
    target.status = "Worker Claimed"
    target.worker_claim_at = now_datetime()
    trip.save(ignore_permissions=True)  # audit-ok: worker + trip resolved from token

    _publish(
        "boarding_claim",
        dispatch_trip,
        {
            "employee": employee,
            "reject_count": cint(target.reject_count),
            "auto_confirm_minutes": get_boarding_setting("boarding_auto_confirm_minutes"),
        },
    )
    return {
        "dispatch_trip": dispatch_trip,
        "status": target.status,
        "reject_count": cint(target.reject_count),
        "auto_confirm_minutes": get_boarding_setting("boarding_auto_confirm_minutes"),
    }


@frappe.whitelist(methods=["POST"])
@rate_limit(key="frappe.request.remote_addr", limit=120, seconds=60)
def driver_confirm_boarding(dispatch_trip, employee, decision):
    """Driver action: confirm or reject a worker's boarding claim (write, driver-scoped).

    ``decision="confirm"`` -> the worker's row becomes ``Boarded``
    (confirm_source=Driver). ``decision="reject"`` -> ``Driver Rejected``,
    reject_count++, and a ``boarding_rejected`` is published to the Dispatch Trip
    room so the worker's poll surfaces the rejection (and can re-claim). Any other
    decision is rejected. Caller must be allowed to act on the trip (own trip for
    a driver, any for Salis staff); resolved server-side."""
    _resolve_trip_for_driver(dispatch_trip)
    decision = (decision or "").strip().lower()
    if decision not in ("confirm", "reject"):
        frappe.throw(_("Decision must be 'confirm' or 'reject'."))

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip)
    target = next((r for r in (trip.boarding_state or []) if r.employee == employee), None)
    if target is None:
        frappe.throw(_("Worker {0} is not on this trip's boarding state.").format(employee))

    if decision == "confirm":
        target.status = "Boarded"
        target.confirm_source = "Driver"
        event, payload = "boarding_update", {"employee": employee, "confirmed": True}
    else:
        target.status = "Driver Rejected"
        target.reject_count = cint(target.reject_count) + 1
        event, payload = "boarding_rejected", {
            "employee": employee,
            "reject_count": cint(target.reject_count),
        }
    trip.save(ignore_permissions=True)  # audit-ok: driver authorised on the trip
    _publish(event, dispatch_trip, payload)

    return {
        "dispatch_trip": dispatch_trip,
        "employee": employee,
        "status": target.status,
        "confirm_source": target.confirm_source or None,
        "reject_count": cint(target.reject_count),
    }


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def worker_trip_boarding(token=None):
    """Worker poll: the worker's current boarding state (read, token-scoped).

    Resolves the token to one Employee and returns their state on today's trip —
    status, the active notify_at + window (for the client countdown),
    wait_count/max, the poll cadence, and any wrong_bus correction (the correct
    trip + driver phone) held as a transient hint from a misboarded scan. The
    driver phone is returned only to the affected worker. Read-only.

    ``{"trip": None}`` with any pending misboard hint when the worker has no
    boardable trip on this bus; a worker not on the trip's boarding state gets a
    Pending default so the client always has a shape to render."""
    from apex_habitat.salis.api.masar import _resolve_worker, _worker_today_dispatch_trip

    employee = _resolve_worker(token)
    window = get_boarding_setting("boarding_notify_window_seconds")
    wait_max = get_boarding_setting("worker_wait_request_max")
    poll_seconds = get_boarding_setting("boarding_active_poll_seconds")
    misboard = _read_misboard(employee)

    resolved = _worker_today_dispatch_trip(employee)
    if not resolved:
        return {
            "trip": None,
            "poll_seconds": poll_seconds,
            "wrong_bus": misboard or None,
        }
    dispatch_trip = resolved[0]

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip)
    # Robust auto-confirm: evaluate the worker-claim timeout on read so the worker
    # sees Boarded the moment the 1/4-hour rule fires, even if no tick ran yet.
    if _apply_auto_confirm(trip):
        trip.save(ignore_permissions=True)  # audit-ok: system timeout, read-time confirm
    row = next((r for r in (trip.boarding_state or []) if r.employee == employee), None)
    state = (
        _state_payload(row, window)
        if row is not None
        else {
            "employee": employee,
            "status": "Pending",
            "notify_count": 0,
            "notify_at": None,
            "notify_window_seconds": window,
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
        }
    )
    return state


@frappe.whitelist(methods=["POST"])
@rate_limit(key="frappe.request.remote_addr", limit=30, seconds=60)
def depart_and_finalize(dispatch_trip):
    """Driver action: depart — mark exhausted Pending workers Absent, close the
    manifest (write, driver-scoped).

    Any still-Pending worker whose notify_count has reached
    boarding_notify_max_count is marked Absent; the rest stay as they are. The
    open Trip Start Log is moved to Completed (its end stamped). Absence only
    applies after the grace window has elapsed (an early depart marks no one
    Absent). Publishes a ``boarding_update``. Returns the boarded vs absent
    counts.

    Caller must be allowed to act on the trip; resolved server-side."""
    _resolve_trip_for_driver(dispatch_trip)

    max_count = get_boarding_setting("boarding_notify_max_count")
    grace_ok = _grace_elapsed(dispatch_trip)

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip)
    # Settle any timed-out worker claims first, so a claimed-then-timed-out worker
    # departs as Boarded, not swept into Absent.
    changed = bool(_apply_auto_confirm(trip))
    boarded = absent = pending = claimed = 0
    for row in trip.boarding_state or []:
        if row.status == "Boarded":
            boarded += 1
            continue
        if row.status == "Absent":
            absent += 1
            continue
        if row.status == "Worker Claimed":
            # An un-timed-out claim is still in flight; keep it (not Absent).
            claimed += 1
            continue
        # Pending / Driver Rejected: exhausted-notify + grace -> Absent.
        if grace_ok and cint(row.notify_count) >= max_count:
            row.status = "Absent"
            absent += 1
            changed = True
        else:
            pending += 1
    if changed:
        trip.save(ignore_permissions=True)  # audit-ok: driver authorised on the trip

    _close_trip_log(dispatch_trip)

    # Post each settled outcome to the immutable Trip Boarding Ledger so per-worker
    # boarding reports stay stable when the operational boarding_state child is
    # later edited. Best-effort: a posting failure must never abort the finalize.
    try:
        from apex_habitat.salis.boarding_engine import post_trip_boarding

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
    )
    return {
        "dispatch_trip": dispatch_trip,
        "boarded": boarded,
        "absent": absent,
        "pending": pending,
        "claimed": claimed,
        "grace_elapsed": grace_ok,
    }


def _close_trip_log(dispatch_trip):
    """Move the trip's open draft Trip Start Log to Completed with an end stamp.
    The headcount log is the manifest record; finalize closes it. No-op when no
    open log exists (the trip never had a boarding event)."""
    name = frappe.db.get_value(
        "Trip Start Log", {"dispatch_trip": dispatch_trip, "docstatus": 0}, "name"
    )
    if not name:
        return
    log = frappe.get_doc("Trip Start Log", name)
    log.status = "Completed"
    if not log.end_datetime:
        log.end_datetime = now_datetime()
    log.save(ignore_permissions=True)  # audit-ok: driver authorised on the trip
