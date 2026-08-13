# Copyright (c) 2026, afmcoltd
"""Salis Driver Portal — execution endpoints (split from the driver_portal god module). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe
from frappe import _

from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
    _resolve_my_trip,
    _resolve_trip_route_stop,
    _open_trip_log,
    _stop_progress_map,
)


def _trip_log_state(driver, dispatch_trip):
    """The driver's Trip Start Log state for a trip as the portal's display shape.
	Mirrors the projection ``_next_trip_today`` attaches, so a start/complete response
	updates the card reactively with no extra round-trip."""
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
    """Mark the driver's own trip Started, creating its Trip Start Log (write).

	Identity-scoped: the driver is resolved credential-first and the trip is honoured
	only when it belongs to that driver (``_resolve_my_trip``). Gets-or-creates the
	Trip Start Log for (trip, driver) and stamps ``start_datetime``; idempotent — a
	second tap returns the existing state rather than duplicating. The Driver holds an
	``if_owner`` DocPerm on Trip Start Log, and the write is server-authoritative
	(driver resolved credential-first), so ``ignore_permissions`` is set. No GL — Trip Start
	Log is a headcount/execution record only."""
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
        doc.insert(ignore_permissions=True)
    return _trip_log_state(driver, dispatch_trip)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def complete_my_trip(dispatch_trip):
    """Mark the driver's own trip Completed on its Trip Start Log (write).

	Identity-scoped (``_resolve_my_trip``). Updates the existing log's status to
	Completed and stamps ``end_datetime``; if the driver never tapped start, the log is
	created and immediately completed so the day still records execution. Server-
	authoritative, so ``ignore_permissions`` is set. No GL."""
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
    doc.flags.ignore_permissions = True
    doc.save() if not doc.is_new() else doc.insert()
    return _trip_log_state(driver, dispatch_trip)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def mark_stop_progress(dispatch_trip, route_stop, done=1, sequence=None, stop_name=None):
    """Mark one route stop done/undone on the driver's STARTED trip (write).

	Persists a Trip Stop Progress row on the trip's open Trip Start Log so per-stop
	completion survives a reload. Identity-scoped (``_resolve_my_trip``); requires the
	trip to be started (an open Trip Start Log must exist — the driver taps Start first).
	Idempotent and reversible: a stop already tracked is updated in place (re-marking the
	same state is a no-op), and ``done=0`` clears it. ``route_stop`` is the source Route
	Stop child row name — the stable key matched across reloads. Server-authoritative, so
	``ignore_permissions`` is set. No GL."""
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
    log.flags.ignore_permissions = True
    log.save()
    return {
        "route_stop": route_stop,
        "done": bool(done),
        "stop_progress": _stop_progress_map(dispatch_trip, driver),
    }
