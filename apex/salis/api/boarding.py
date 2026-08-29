# Copyright (c) 2026, afmcoltd

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
    return get_encryption_key().encode("utf-8")


def _sign(body: bytes) -> str:
    return hmac.new(_secret(), body, hashlib.sha256).hexdigest()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(txt: str) -> bytes:
    pad = "=" * (-len(txt) % 4)
    return base64.urlsafe_b64decode(txt + pad)


def _issue_token(dispatch_trip: str, worker: str) -> str:
    payload = {
        "dt": dispatch_trip,
        "w": worker,
        "iat": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"{_b64e(body)}.{_sign(body)}"


def _verify_token(token: str) -> dict | None:
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
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_staff(user: str | None = None) -> bool:
    return has_any_role(user, STAFF_ROLES)


def _presented_driver() -> str | None:
    raw, was_presented = presented_token(DRIVER)
    if not was_presented:
        return None
    return resolve_portal_subject(DRIVER, raw, required=True)


def _authorize_scan_actor() -> str:
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
    if not getattr(frappe.local, "request", None):
        return

    command = frappe.form_dict.get("cmd") or endpoint
    charge_window(
        f"rl:{command}:{scope}:{identity}",
        window_seconds,
        limit,
    )


def _enforce_scan_rate_limit(scope: str, identity: str, limit: int) -> None:
    _charge_request_window(
        scope,
        identity,
        limit,
        SCAN_RATE_WINDOW_SECONDS,
        "apex.salis.api.boarding.scan_boarding_pass",
    )


def _enforce_scan_actor_rate_limit(actor: str) -> None:
    _enforce_scan_rate_limit("scan-actor", actor, SCAN_ACTOR_LIMIT)


def _enforce_scan_unresolved_ip_rate_limit() -> None:
    if not getattr(frappe.local, "request", None):
        return
    ip = getattr(frappe.local, "request_ip", None)
    if not ip:
        return
    _enforce_scan_rate_limit("scan-unresolved-ip", ip, SCAN_UNRESOLVED_IP_LIMIT)


def _transport_peer() -> str | None:
    return getattr(getattr(frappe.local, "request", None), "remote_addr", None)


def _enforce_pass_read_rate_limit() -> None:
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
    from apex.salis.api.boarding_flow import _manifest_employees

    return {e for e in _manifest_employees(dispatch_trip, transport_request) if e}


def get_or_create_log(dispatch_trip: str, driver: str | None = None) -> "frappe.model.document.Document":
    frappe.db.get_value("Dispatch Trip", dispatch_trip, "name", for_update=True)
    existing = frappe.db.get_value(
        "Trip Start Log",
        {"dispatch_trip": dispatch_trip, "docstatus": 0},
        "name",
        for_update=True,
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
    driver = trip.get("driver") if trip else None
    doc = frappe.get_doc(
        {
            "doctype": "Boarding Scan Log",
            "dispatch_trip": dispatch_trip,
            "trip_start_log": trip_start_log,
            "transport_request": trip.get("transport_request") if trip else None,
            "driver": driver,
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
    with as_capacity(DRIVER, driver):
        doc.insert()
    return doc.name


@frappe.whitelist(allow_guest=True)
def get_boarding_pass(dispatch_trip, worker):
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
    log = get_or_create_log(dispatch_trip, driver)

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
