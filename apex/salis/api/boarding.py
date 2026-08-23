# Copyright (c) 2026, afmcoltd
"""Salis driver passenger-boarding — QR boarding pass + scan-validate.

The pass token is HMAC-signed (per-site key) so it cannot be forged client-side
and is bound to (trip, worker); every scan attempt is recorded as an immutable
Boarding Scan Log row. No GL/money. A driver may only act on their own trips
(resolved server-side); the client never supplies a driver id.

The Boarding Scan Log write (``_log_scan``) keeps ``ignore_permissions``: it is an ``in_create``
audit record no role may write by hand, and one on the scan log would make the audit trail
forgeable from the Desk. The Trip Start Log writes (get-or-create + the boarding event append) run
inside ``as_capacity(DRIVER, driver)`` instead — it is the driver's own execution record, and
``apex.salis.permissions._trip_start_log_capacity_verdict`` refuses the write when the log's own
driver is not the identity the HMAC-verified pass / server-resolved trip ownership check bound.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime, time_diff_in_seconds
from frappe.utils.password import get_encryption_key

from apex.apex_core.utils.portal_identity import (
    DRIVER,
    as_capacity,
    presented_token,
    resolve_portal_subject,
)
from apex.apex_core.utils.rate_window import charge_window
from apex.salis.utils import get_driver_for_user, has_any_role


PASS_TTL_HOURS = 24
SCAN_ACTOR_LIMIT = 60
SCAN_UNRESOLVED_IP_LIMIT = 60
SCAN_RATE_WINDOW_SECONDS = 60

PASS_ADDRESS_LIMIT = 120
PASS_PEER_LIMIT = 1200
PASS_RATE_WINDOW_SECONDS = 60

STAFF_ROLES = (
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
    "System Manager",
)


def _secret() -> bytes:
    """Per-site HMAC key. Reuses the site encryption key so no new secret has to
    be provisioned and the signature is stable across workers/restarts."""
    return get_encryption_key().encode("utf-8")


def _sign(body: bytes) -> str:
    """Computes the HMAC-SHA256 signature of the given bytes using the site's boarding secret."""
    return hmac.new(_secret(), body, hashlib.sha256).hexdigest()


def _b64e(raw: bytes) -> str:
    """Encodes bytes as unpadded URL-safe base64 text."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(txt: str) -> bytes:
    """Decodes unpadded URL-safe base64 text back into bytes."""
    pad = "=" * (-len(txt) % 4)
    return base64.urlsafe_b64decode(txt + pad)


def _issue_token(dispatch_trip: str, worker: str) -> str:
    """Build a signed pass token binding (trip, worker, issue-time).

    ``body`` is what ``_sign`` hashes below; its bytes are the HMAC input, not a
    value to reparse or reshape.
    """
    payload = {
        "dt": dispatch_trip,
        "w": worker,
        "iat": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"{_b64e(body)}.{_sign(body)}"


def _verify_token(token: str) -> dict | None:
    """Return the decoded payload when the signature is intact, else None. A
    tampered body or a wrong/forged signature both fail closed (constant-time
    compare).

    ``body`` is parsed only after it verified against the HMAC above, and it is
    ``bytes`` here, not ``str`` — a helper that skips non-``str`` input would
    return it unparsed instead of a payload dict.
    """
    if not token or "." not in token:
        return None
    encoded, sig = token.rsplit(".", 1)
    try:
        body = _b64d(encoded)
    except Exception:
        return None
    if not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        return json.loads(body)
    except Exception:
        return None


def _token_hash(token: str) -> str:
    """SHA-256 of the raw token — stored on the log instead of the token itself."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_staff(user: str | None = None) -> bool:
    """True when the user may authorise a scan, per this module's own STAFF_ROLES."""
    return has_any_role(user, STAFF_ROLES)


def _presented_driver() -> str | None:
    """Resolve a presented driver credential before any lookup or write."""
    raw, was_presented = presented_token(DRIVER)
    if not was_presented:
        return None
    return resolve_portal_subject(DRIVER, raw, required=True)


def _authorize_scan_actor() -> str:
    """Require an authorized actor and return its server-resolved rate identity."""
    credential_driver = _presented_driver()
    if credential_driver:
        return credential_driver
    if _is_staff():
        return f"staff:{frappe.session.user}"
    session_driver = get_driver_for_user()
    if session_driver:
        return session_driver
    frappe.throw(
        _("You may only handle boarding for your own trips."),
        frappe.PermissionError,
    )


def _charge_request_window(
    scope: str, identity: str, limit: int, window_seconds: int, endpoint: str
) -> None:
    """Charge this request against one named window.

    """
    if not getattr(frappe.local, "request", None):
        return

    command = frappe.form_dict.get("cmd") or endpoint
    charge_window(
        f"rl:{command}:{scope}:{identity}",
        window_seconds,
        limit,
    )


def _enforce_scan_rate_limit(scope: str, identity: str, limit: int) -> None:
    """Charge a scan bucket only after its identity is selected server-side."""
    _charge_request_window(
        scope,
        identity,
        limit,
        SCAN_RATE_WINDOW_SECONDS,
        "apex.salis.api.boarding.scan_boarding_pass",
    )


def _enforce_scan_actor_rate_limit(actor: str) -> None:
    """Apply the scan peak limit after actor authority is resolved server-side."""
    _enforce_scan_rate_limit("scan-actor", actor, SCAN_ACTOR_LIMIT)


def _enforce_scan_unresolved_ip_rate_limit() -> None:
    """Bound rejected scan credentials without charging authenticated NAT peers.

    Guarded like the bad-token limiter it shares a counter with
    (portal_identity._throttle_bad_token_attempt), because here the bucket IS
    the address, so a request carrying none must decline to count. Reading it bare
    raised AttributeError where the attribute is unset, and where it is merely None
    (``frappe.init``'s value until ``frappe.app`` fills it) pooled every addressless
    caller into ONE bucket — the opposite of a per-address ceiling. The sibling actor
    limiter needs no address guard: its identity comes from the session, not the
    connection, so it is never absent.
    """
    if not getattr(frappe.local, "request", None):
        return
    ip = getattr(frappe.local, "request_ip", None)
    if not ip:
        return
    _enforce_scan_rate_limit("scan-unresolved-ip", ip, SCAN_UNRESOLVED_IP_LIMIT)


def _transport_peer() -> str | None:
    """The address the CONNECTION came from -- the one a caller cannot choose.

    Behind a reverse proxy this is the EDGE, not the caller, so it identifies one
    connection rather than one person -- which is exactly why it carries its own far
    looser ceiling instead of the per-address one.

    """
    return getattr(getattr(frappe.local, "request", None), "remote_addr", None)


def _enforce_pass_read_rate_limit() -> None:
    """Bound the pass read on the address it CLAIMS and the connection it CAME FROM.

    The address window is unchanged: the same 120 per minute on the same
    ``request_ip``, so nothing that was refused before is admitted now. What it never
    had is a bound a forger cannot step out of -- ``request_ip`` is whatever the first
    X-Forwarded-For entry says, so one caller rotating that header opens a fresh
    window per request and the ceiling never arrives. The peer window is the one that
    does not move under it.

    An identity that is absent declines to charge rather than pooling every such caller
    into a bucket named after nothing -- the same call the sibling scan limiter makes,
    because a shared bucket is not a ceiling, it is a way for one caller to 429 the rest.

    """
    for scope, identity, limit in (
        ("pass-address", getattr(frappe.local, "request_ip", None), PASS_ADDRESS_LIMIT),
        ("pass-peer", _transport_peer(), PASS_PEER_LIMIT),
    ):
        if not identity:
            continue
        _charge_request_window(
            scope,
            identity,
            limit,
            PASS_RATE_WINDOW_SECONDS,
            "apex.salis.api.boarding.get_boarding_pass",
        )


def _resolve_trip(dispatch_trip: str, ptype: str = "read") -> dict:
    """Authorize the actor before loading the trip, then enforce trip scope.

    Salis staff may act on any trip only without a driver credential; a
    presented credential is confined to its own driver's trips. A non-staff
    session must be linked to a driver before the trip lookup, so missing trip
    names cannot become an existence oracle for unauthenticated callers.

    ``STAFF_ROLES`` is a role-set intersection, and two of its members — Fleet
    Project Manager and Fleet Supervisor — are absent from
    ``permissions.UNSCOPED_ROLES``, i.e. they are precisely the scoped roles the
    Dispatch Trip row-scope exists for. Holding one of them says the actor may act
    on THEIR project's trips, never on any trip named. The row read below cannot
    make that distinction: ``frappe.db.get_value`` runs no permission layer, so
    neither the ``permission_query_conditions`` fragment nor the ``has_permission``
    hook registered for Dispatch Trip (hooks.py) is consulted. The staff branch
    therefore asks the document gate explicitly, which dispatches
    ``permissions.project_scoped_has_permission`` ->
    ``_dispatch_trip_has_permission`` — the assigned driver and the named route
    supervisor pass, an out-of-project trip is refused.

    ``ptype`` is the right the CALLER is about to exercise: the manifest reads ask
    for "read", the endpoints that mark workers Absent, drop a boarding event or
    insert one ask for "write". The credential and linked-driver paths are already
    confined by the ``driver`` key in the lookup itself and are not re-checked.
    """
    credential_driver = _presented_driver()
    staff_actor = False
    session_driver = None
    if not credential_driver:
        staff_actor = _is_staff()
        if not staff_actor:
            session_driver = get_driver_for_user()
            if not session_driver:
                frappe.throw(
                    _("You may only handle boarding for your own trips."),
                    frappe.PermissionError,
                )

    actor_driver = credential_driver or session_driver
    trip_identifier = (
        dispatch_trip
        if staff_actor
        else {"name": dispatch_trip, "driver": actor_driver}
    )
    trip = frappe.db.get_value(
        "Dispatch Trip",
        trip_identifier,
        ["name", "driver", "transport_request", "trip_date"],
        as_dict=True,
    )
    if not trip:
        if not staff_actor:
            frappe.throw(
                _("Trip not found or not permitted."),
                frappe.PermissionError,
            )
        frappe.throw(_("Trip not found."), frappe.DoesNotExistError)

    if staff_actor:
        frappe.has_permission("Dispatch Trip", ptype, doc=dispatch_trip, throw=True)
    return trip


def _trip_manifest_workers(
    transport_request: str | None, dispatch_trip: str | None = None
) -> set[str]:
    """The set of Employee ids on the trip's expected manifest — the UNION of the
    Route Plan Transport Request's workers and every assigned-request's workers. A
    pass is only honoured for a worker actually on this union. Resolved through the
    boarding_flow helper so the QR gate and the boarding-state seeding share one
    definition of "on this trip"."""
    from apex.salis.api.boarding_flow import _manifest_employees

    return {e for e in _manifest_employees(dispatch_trip, transport_request) if e}


def _get_or_create_log(dispatch_trip: str, driver: str | None = None) -> "frappe.model.document.Document":
    """Return the open Trip Start Log for the trip, creating a draft one if none
    exists yet. One scan should not need a separately-opened log — the first valid
    scan opens it. A submitted/cancelled log is not reused; a fresh draft is made
    so post-submission scans never mutate a closed record.

    ``driver`` is the server-resolved driver the create is authorised under — set on the
    doc directly (not left to its ``fetch_from``) so the create-permission check already
    sees the field it must match against the ``as_capacity`` identity."""
    existing = frappe.db.get_value(
        "Trip Start Log",
        {"dispatch_trip": dispatch_trip, "docstatus": 0},
        "name",
    )
    if existing:
        return frappe.get_doc("Trip Start Log", existing)

    log = frappe.get_doc(
        {
            "doctype": "Trip Start Log",
            "dispatch_trip": dispatch_trip,
            "driver": driver,
            "status": "Started",
            "start_datetime": now_datetime(),
        }
    )
    with as_capacity(DRIVER, driver):
        log.insert()
    from apex.salis.api.boarding_flow import ensure_trip_boarding_state

    ensure_trip_boarding_state(dispatch_trip)
    return log


def already_boarded(log, worker: str) -> bool:
    """True when the worker already has a REGISTERED boarding event on this log.

    Public because three sibling entry points — the Masar confirm, the manual desk and
    the boarding flow — must answer this the same way; a second copy anywhere makes a
    re-confirm stop being idempotent and double-counts the headcount.

    An UNREGISTERED row never counts: it records someone boarded without a worker
    record, so it can neither be matched to ``worker`` nor block their own boarding.
    """
    return any(
        (row.worker == worker and not row.is_unregistered)
        for row in (log.boarding_events or [])
    )


def _log_scan(
    dispatch_trip,
    trip,
    worker,
    result,
    token,
    trip_start_log=None,
    boarding_created=0,
    accommodation_building=None,
    notes=None,
):
    """Write one immutable Boarding Scan Log row for this scan attempt."""
    doc = frappe.get_doc(
        {
            "doctype": "Boarding Scan Log",
            "dispatch_trip": dispatch_trip,
            "trip_start_log": trip_start_log,
            "transport_request": trip.get("transport_request") if trip else None,
            "driver": trip.get("driver") if trip else None,
            "employee": worker,
            "accommodation_building": accommodation_building,
            "result": result,
            "method": "QR",
            "scanned_at": now_datetime(),
            "boarding_event_created": cint(boarding_created),
            "pass_token_hash": _token_hash(token) if token else None,
            "notes": notes,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist(allow_guest=True)
def get_boarding_pass(dispatch_trip, worker):
    """Issue a signed QR boarding pass for ``worker`` on ``dispatch_trip`` (read).

    Caller scope is resolved credential-first. A presented driver credential is
    confined to its own trip; staff fallback applies only without one. ``worker``
    must be on the trip's Transport Request manifest. Returns the pass token plus
    a ``qr_payload`` (the same token, what the SPA renders as a QR image) and
    display fields. Issues no DB write — a pass is just a signed claim; it only
    matters when scanned.

    Rate-limited in the body rather than by ``@rate_limit`` because the ceiling this
    read needs is keyed on the transport peer, which that decorator's ``key`` cannot
    name — see _enforce_pass_read_rate_limit. Charged first, before any lookup, which
    is where the decorator charged it."""
    _enforce_pass_read_rate_limit()
    trip = _resolve_trip(dispatch_trip)

    manifest = _trip_manifest_workers(trip.get("transport_request"), dispatch_trip)
    if worker not in manifest:
        frappe.throw(
            _("Worker {0} is not on this trip's manifest.").format(worker)
        )

    token = _issue_token(dispatch_trip, worker)
    return {
        "dispatch_trip": dispatch_trip,
        "worker": worker,
        "worker_name": frappe.db.get_value("Employee", worker, "employee_name"),
        "pass_token": token,
        "qr_payload": token,
        "expires_in_hours": PASS_TTL_HOURS,
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
def scan_boarding_pass(pass_token, accommodation_building=None, stop_name=None):
    """Validate a scanned QR boarding pass and log the boarding (write).

    On a **Valid** first scan: get-or-create the trip's draft Trip Start Log and
    append a Trip Boarding Event row for the worker (method ``QR``) — this is the
    boarding event. A repeat scan of the same worker on the same trip is a
    **Duplicate** (no second row). A tampered/forged token is **Invalid Token**; a
    pass whose worker is no longer on the manifest is **Wrong Trip**; a pass past
    its TTL is **Expired**. EVERY outcome writes a Boarding Scan Log row, so the
    audit trail is complete. Returns the result and (when created) the log id and
    boarding row count. No GL is posted."""
    try:
        actor = _authorize_scan_actor()
    except frappe.PermissionError:
        _enforce_scan_unresolved_ip_rate_limit()
        raise
    _enforce_scan_actor_rate_limit(actor)
    payload = _verify_token(pass_token)

    if not payload:
        log_name = _log_scan(
            None, None, None, "Invalid Token", pass_token,
            notes="Signature verification failed.",
        )
        return {"result": "Invalid Token", "scan_log": log_name}

    dispatch_trip = payload.get("dt")
    worker = payload.get("w")
    trip = _resolve_trip(dispatch_trip, "write")

    issued = get_datetime(payload.get("iat"))
    age_hours = time_diff_in_seconds(now_datetime(), issued) / 3600.0 if issued else None
    if age_hours is None or age_hours > PASS_TTL_HOURS:
        log_name = _log_scan(
            dispatch_trip, trip, worker, "Expired", pass_token,
            notes="Pass is past its validity window.",
        )
        return {"result": "Expired", "scan_log": log_name}

    if worker not in _trip_manifest_workers(trip.get("transport_request"), dispatch_trip):
        log_name = _log_scan(
            dispatch_trip, trip, worker, "Wrong Trip", pass_token,
            notes="Worker is not on this trip's manifest.",
        )
        from apex.salis.api.boarding_flow import build_wrong_bus_result

        correction = build_wrong_bus_result(dispatch_trip, worker)
        if correction:
            return {"result": "Wrong Trip", "scan_log": log_name, **correction}
        return {"result": "Wrong Trip", "scan_log": log_name}

    frappe.db.get_value("Dispatch Trip", dispatch_trip, "name", for_update=True)

    driver = trip.get("driver")
    log = _get_or_create_log(dispatch_trip, driver)

    if already_boarded(log, worker):
        log_name = _log_scan(
            dispatch_trip, trip, worker, "Duplicate", pass_token,
            trip_start_log=log.name, notes="Worker already boarded this trip.",
        )
        return {
            "result": "Duplicate",
            "scan_log": log_name,
            "trip_start_log": log.name,
        }

    log.append(
        "boarding_events",
        {
            "worker": worker,
            "stop_name": stop_name,
            "accommodation_building": accommodation_building,
            "boarded_at": now_datetime(),
            "method": "QR",
        },
    )
    with as_capacity(DRIVER, driver):
        log.save()

    scan_log = _log_scan(
        dispatch_trip, trip, worker, "Valid", pass_token,
        trip_start_log=log.name, boarding_created=1,
        accommodation_building=accommodation_building,
    )
    from apex.salis.api.boarding_flow import mark_boarded

    mark_boarded(dispatch_trip, worker)
    return {
        "result": "Valid",
        "scan_log": scan_log,
        "trip_start_log": log.name,
        "worker": worker,
        "boarded_count": log.boarded_count,
    }
