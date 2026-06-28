# Copyright (c) 2026, AFMCO and contributors
"""Salis driver passenger-boarding — QR boarding pass + scan-validate.

The pass token is HMAC-signed (per-site key) so it cannot be forged client-side
and is bound to (trip, worker); every scan attempt is recorded as an immutable
Boarding Scan Log row. No GL/money. A driver may only act on their own trips
(resolved server-side); the client never supplies a driver id.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, get_datetime, now_datetime
from frappe.utils.password import get_encryption_key

from apex_habitat.salis.utils import get_driver_for_user

# A pass is valid for this many hours after issue (a trip is a same-day event).
PASS_TTL_HOURS = 24

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
    return hmac.new(_secret(), body, hashlib.sha256).hexdigest()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(txt: str) -> bytes:
    pad = "=" * (-len(txt) % 4)
    return base64.urlsafe_b64decode(txt + pad)


def _issue_token(dispatch_trip: str, worker: str) -> str:
    """Build a signed pass token binding (trip, worker, issue-time)."""
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
    compare)."""
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
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return bool(set(frappe.get_roles(user)) & set(STAFF_ROLES))


def _driver_for_user(user: str | None = None) -> str | None:
    # Thin alias of the shared salis.utils resolver (single source); preserves the
    # soft None-on-unlinked behaviour _resolve_trip's own-trip gate depends on.
    return get_driver_for_user(user)


def _resolve_trip(dispatch_trip: str) -> dict:
    """Load the trip and enforce that the caller may act on it: Salis staff may
    act on any trip; a driver only on their own. Fails closed for everyone else."""
    trip = frappe.db.get_value(
        "Dispatch Trip",
        dispatch_trip,
        ["name", "driver", "transport_request", "trip_date"],
        as_dict=True,
    )
    if not trip:
        frappe.throw(_("Trip not found."), frappe.DoesNotExistError)

    if _is_staff():
        return trip

    driver = _driver_for_user()
    if not driver or trip.driver != driver:
        frappe.throw(
            _("You may only handle boarding for your own trips."),
            frappe.PermissionError,
        )
    return trip


def _trip_manifest_workers(
    transport_request: str | None, dispatch_trip: str | None = None
) -> set[str]:
    """The set of Employee ids on the trip's expected manifest — the UNION of the
    Route Plan Transport Request's workers and every assigned-request's workers. A
    pass is only honoured for a worker actually on this union. Resolved through the
    boarding_flow helper so the QR gate and the boarding-state seeding share one
    definition of "on this trip"."""
    from apex_habitat.salis.api.boarding_flow import _manifest_employees

    return {e for e in _manifest_employees(dispatch_trip, transport_request) if e}


def _get_or_create_log(dispatch_trip: str) -> "frappe.model.document.Document":
    """Return the open Trip Start Log for the trip, creating a draft one if none
    exists yet. One scan should not need a separately-opened log — the first valid
    scan opens it. A submitted/cancelled log is not reused; a fresh draft is made
    so post-submission scans never mutate a closed record."""
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
            "status": "Started",
            "start_datetime": now_datetime(),
        }
    )
    log.insert(ignore_permissions=True)  # audit-ok: trip authorised in _resolve_trip
    # The trip has now started: seed the per-worker boarding state from the
    # manifest so the boarding/departure flow has its rows from the first scan.
    from apex_habitat.salis.api.boarding_flow import ensure_trip_boarding_state

    ensure_trip_boarding_state(dispatch_trip)
    return log


def _already_boarded(log, worker: str) -> bool:
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
            "worker": worker,
            "accommodation_building": accommodation_building,
            "result": result,
            "method": "QR",
            "scanned_at": now_datetime(),
            "boarding_event_created": cint(boarding_created),
            "pass_token_hash": _token_hash(token) if token else None,
            "notes": notes,
        }
    )
    doc.insert(ignore_permissions=True)  # audit-ok: scan attempt is always recorded
    return doc.name


# Per-IP throttle matching the Masar read endpoints: pass issuance is a read but
# must not be drivable as a bulk token-minting oracle from one address.
@frappe.whitelist()
@rate_limit(key="frappe.request.remote_addr", limit=60, seconds=60)
def get_boarding_pass(dispatch_trip, worker):
    """Issue a signed QR boarding pass for ``worker`` on ``dispatch_trip`` (read).

    The caller must be allowed to act on the trip (own trip for a driver, any trip
    for Salis staff), and ``worker`` must be on the trip's Transport Request
    manifest. Returns the pass token plus a ``qr_payload`` (the same token, what
    the SPA renders as a QR image) and display fields. Issues no DB write — a pass
    is just a signed claim; it only matters when scanned."""
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


@frappe.whitelist(methods=["POST"])
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
    payload = _verify_token(pass_token)

    # [#bsl-forged] A bad signature is logged with no trip context — we cannot
    # trust any field inside a forged token.
    if not payload:
        log_name = _log_scan(
            None, None, None, "Invalid Token", pass_token,
            notes="Signature verification failed.",
        )
        return {"result": "Invalid Token", "scan_log": log_name}

    dispatch_trip = payload.get("dt")
    worker = payload.get("w")
    trip = _resolve_trip(dispatch_trip)

    # [#bsl-expiry]
    issued = get_datetime(payload.get("iat"))
    age_hours = (now_datetime() - issued).total_seconds() / 3600.0 if issued else None
    if age_hours is None or age_hours > PASS_TTL_HOURS:
        log_name = _log_scan(
            dispatch_trip, trip, worker, "Expired", pass_token,
            notes="Pass is past its validity window.",
        )
        return {"result": "Expired", "scan_log": log_name}

    # [#bsl-manifest] The worker must still be on the trip's manifest. When they
    # are not, try to resolve their REAL trip today and return a structured
    # WRONG_BUS correction (correct trip + that driver's phone, for the worker to
    # find the right bus); fall back to the plain Wrong Trip result otherwise. The
    # scan attempt is recorded either way.
    if worker not in _trip_manifest_workers(trip.get("transport_request"), dispatch_trip):
        log_name = _log_scan(
            dispatch_trip, trip, worker, "Wrong Trip", pass_token,
            notes="Worker is not on this trip's manifest.",
        )
        from apex_habitat.salis.api.boarding_flow import build_wrong_bus_result

        correction = build_wrong_bus_result(dispatch_trip, worker)
        if correction:
            return {"result": "Wrong Trip", "scan_log": log_name, **correction}
        return {"result": "Wrong Trip", "scan_log": log_name}

    # [#bsl-race] Serialize concurrent valid scans of the SAME trip: lock the
    # Dispatch Trip row before get-or-create-log + the dup-check + append. Two
    # scans of one (trip,worker) would otherwise both pass _already_boarded on a
    # stale read and write two Trip Start Logs / two boarding events; the lock
    # makes the second wait until the first commits, then it resolves to Duplicate.
    frappe.db.get_value("Dispatch Trip", dispatch_trip, "name", for_update=True)

    log = _get_or_create_log(dispatch_trip)

    # [#bsl-dup] Idempotent: a second scan of the same worker logs no new row.
    if _already_boarded(log, worker):
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
    log.save(ignore_permissions=True)  # audit-ok: trip authorised in _resolve_trip

    scan_log = _log_scan(
        dispatch_trip, trip, worker, "Valid", pass_token,
        trip_start_log=log.name, boarding_created=1,
        accommodation_building=accommodation_building,
    )
    # Reflect the boarding into the trip's flow state (Pending -> Boarded).
    from apex_habitat.salis.api.boarding_flow import mark_boarded

    mark_boarded(dispatch_trip, worker)
    return {
        "result": "Valid",
        "scan_log": scan_log,
        "trip_start_log": log.name,
        "worker": worker,
        "boarded_count": log.boarded_count,
    }
