# Copyright (c) 2026, afmcoltd
"""Salis Driver Portal — boarding endpoints (split from the driver_portal god module). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe
from frappe import _

from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
)


MAX_MANUAL_BOARD_WORKERS = 100


def _manual_worker_ids(workers):
    """Return one bounded, stable-deduplicated list of Employee ids."""
    requested = workers
    if isinstance(requested, str):
        try:
            requested = frappe.parse_json(requested)
        except Exception:
            frappe.throw(_("Workers must be a JSON list of worker IDs."))
    if not isinstance(requested, list):
        frappe.throw(_("Workers must be a JSON list of worker IDs."))
    if len(requested) > MAX_MANUAL_BOARD_WORKERS:
        frappe.throw(
            _("Select no more than {0} workers at a time.").format(
                MAX_MANUAL_BOARD_WORKERS
            )
        )

    unique = []
    seen = set()
    for worker in requested:
        if not isinstance(worker, str) or not worker.strip():
            frappe.throw(_("Each worker ID must be a non-empty string."))
        worker = worker.strip()
        if worker not in seen:
            seen.add(worker)
            unique.append(worker)
    if not unique:
        frappe.throw(_("Select at least one worker to board."))
    return unique


def _manifest_for_board(transport_request):
    """Manifest workers for a trip, each as ``{employee, employee_name, boarded}``
	for the manual-boarding checklist. ``boarded`` is filled by the caller against the
	trip's Trip Start Log so the sheet shows who is already aboard. Read-only."""
    rows = frappe.get_all(
        "Transport Request Worker",
        filters={"parent": transport_request, "parenttype": "Transport Request"},
        fields=["employee", "pickup_point"],
        order_by="idx asc",
    )
    emp_ids = [r["employee"] for r in rows if r.get("employee")]
    names = dict(
        frappe.get_all(
            "Employee",
            filters={"name": ["in", emp_ids]},
            fields=["name", "employee_name"],
            as_list=True,
        )
    ) if emp_ids else {}
    out = []
    for r in rows:
        if not r.get("employee"):
            continue
        out.append(
            {
                "employee": r["employee"],
                "employee_name": names.get(r["employee"]),
                "pickup_point": r.get("pickup_point"),
                "boarded": False,
            }
        )
    return out


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def manual_boarding_sheet(dispatch_trip):
    """The manual-boarding checklist for the driver's own trip (read).

	The fallback when a pass can't be scanned: returns the trip's manifest workers
	with an ``boarded`` flag (already aboard via any prior scan/manual board), so the
	SPA can render a tick-list. Identity-scoped — the driver is resolved
	credential-first and the trip honoured only when it belongs to that driver (the same
	guard the boarding writes use). Read-only, no commit."""
    _require_enabled()
    from apex.salis.api import boarding

    _resolve_driver()
    trip = boarding._resolve_trip(dispatch_trip)

    workers = _manifest_for_board(trip.get("transport_request"))
    log_name = frappe.db.get_value(
        "Trip Start Log", {"dispatch_trip": dispatch_trip, "docstatus": 0}, "name"
    )
    if log_name:
        boarded = set(
            frappe.get_all(
                "Trip Boarding Event",
                filters={"parent": log_name, "parenttype": "Trip Start Log", "is_unregistered": 0},
                pluck="worker",
            )
        )
        for w in workers:
            w["boarded"] = w["employee"] in boarded
    return {
        "dispatch_trip": dispatch_trip,
        "route_name": (
            frappe.db.get_value("Route Plan", trip.get("route_plan"), "route_name")
            if trip.get("route_plan")
            else None
        ),
        "workers": workers,
        "boarded_count": sum(1 for w in workers if w["boarded"]),
        "expected_count": len(workers),
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def manual_board_workers(dispatch_trip, workers, stop_name=None, accommodation_building=None):
    """Mark one or more manifest workers aboard MANUALLY (write) — the no-scan fallback.

	Mirrors ``boarding.scan_boarding_pass``'s write path minus the token check: for each
	requested worker it get-or-creates the trip's draft Trip Start Log, appends a Trip
	Boarding Event (method ``Manual``), and writes a Boarding Scan Log audit row (method
	``Manual``, result ``Valid``) — so a manual board appears in the same audit trail a
	scan does. Identity-scoped: the driver is resolved credential-first and the trip is
	honoured only when it belongs to that driver (``boarding._resolve_trip``); only workers
	on the trip's manifest are accepted, and an already-aboard worker is a no-op (idempotent,
	like a Duplicate scan). ``workers`` is a JSON list of at most 100 Employee ids;
	duplicates are processed once in first-seen order.
	Returns the per-worker outcome and the updated boarded count. No GL."""
    _require_enabled()
    from apex.salis.api import boarding

    _resolve_driver()
    requested = _manual_worker_ids(workers)
    trip = boarding._resolve_trip(dispatch_trip)

    frappe.db.get_value("Dispatch Trip", dispatch_trip, "name", for_update=True)
    manifest = boarding._trip_manifest_workers(trip.get("transport_request"))
    log = boarding._get_or_create_log(dispatch_trip)

    boarded, skipped = [], []
    for worker in requested:
        if worker not in manifest:
            _log_manual_scan(dispatch_trip, trip, worker, "Wrong Trip", log.name,
                              notes="Worker is not on this trip's manifest.")
            skipped.append({"worker": worker, "result": "Wrong Trip"})
            continue
        if boarding._already_boarded(log, worker):
            _log_manual_scan(dispatch_trip, trip, worker, "Duplicate", log.name,
                             notes="Worker already boarded this trip.")
            skipped.append({"worker": worker, "result": "Duplicate"})
            continue
        log.append(
            "boarding_events",
            {
                "worker": worker,
                "stop_name": stop_name,
                "accommodation_building": accommodation_building,
                "boarded_at": frappe.utils.now_datetime(),
                "method": "Manual",
            },
        )
        boarded.append(worker)

    if boarded:
        log.save(ignore_permissions=True)  # audit-ok
        for worker in boarded:
            _log_manual_scan(dispatch_trip, trip, worker, "Valid", log.name,
                             boarding_created=1, accommodation_building=accommodation_building)

    return {
        "trip_start_log": log.name,
        "boarded": boarded,
        "skipped": skipped,
        "boarded_count": log.boarded_count,
    }


def _log_manual_scan(dispatch_trip, trip, worker, result, trip_start_log,
                     boarding_created=0, accommodation_building=None, notes=None):
    """Write one Boarding Scan Log row for a MANUAL board attempt (method ``Manual``).

	The manual analogue of ``boarding._log_scan`` (which is QR-only and not editable from
	here); same immutable-audit intent so a manual board shows in the Boarding Scan Log
	alongside scans. No pass token exists for a manual board, so ``pass_token_hash`` stays
	null."""
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
            "method": "Manual",
            "scanned_at": frappe.utils.now_datetime(),
            "boarding_event_created": frappe.utils.cint(boarding_created),
        }
    )
    doc.insert(ignore_permissions=True)  # audit-ok
    return doc.name
