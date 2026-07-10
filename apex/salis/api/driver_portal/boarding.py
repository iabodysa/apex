# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver Portal — boarding endpoints (split from the driver_portal god module in P-180). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe
from frappe import _

from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
)


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
	# Resolve every employee_name in ONE query instead of one get_value per row.
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



@frappe.whitelist()
def manual_boarding_sheet(dispatch_trip):
	"""The manual-boarding checklist for the driver's own trip (read).

	The fallback when a pass can't be scanned: returns the trip's manifest workers
	with an ``boarded`` flag (already aboard via any prior scan/manual board), so the
	SPA can render a tick-list. Identity-scoped — the driver is resolved from the
	session and the trip honoured only when it belongs to that driver (the same
	guard the boarding writes use). Read-only, no commit."""
	_require_enabled()
	from apex.salis.api import boarding

	_resolve_driver()  # gate: caller must be a linked driver
	trip = boarding._resolve_trip(dispatch_trip)  # read-only reuse; enforces own-trip (else 403)

	workers = _manifest_for_board(trip.get("transport_request"))
	# Mark who is already aboard from the trip's open Trip Start Log (registered rows).
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



@frappe.whitelist(methods=["POST"])
def manual_board_workers(dispatch_trip, workers, stop_name=None, accommodation_building=None):
	"""Mark one or more manifest workers aboard MANUALLY (write) — the no-scan fallback.

	Mirrors ``boarding.scan_boarding_pass``'s write path minus the token check: for each
	requested worker it get-or-creates the trip's draft Trip Start Log, appends a Trip
	Boarding Event (method ``Manual``), and writes a Boarding Scan Log audit row (method
	``Manual``, result ``Valid``) — so a manual board appears in the same audit trail a
	scan does. Identity-scoped: the driver is resolved from the session and the trip is
	honoured only when it belongs to that driver (``boarding._resolve_trip``); only workers
	on the trip's manifest are accepted, and an already-aboard worker is a no-op (idempotent,
	like a Duplicate scan). ``workers`` is a JSON list (or single id) of Employee ids.
	Returns the per-worker outcome and the updated boarded count. No GL."""
	_require_enabled()
	from apex.salis.api import boarding

	_resolve_driver()  # gate: caller must be a linked driver
	trip = boarding._resolve_trip(dispatch_trip)  # read-only reuse; enforces own-trip (else 403)

	requested = workers
	if isinstance(requested, str):
		try:
			requested = frappe.parse_json(requested)
		except Exception:
			requested = [requested]
	if not isinstance(requested, (list, tuple)):
		requested = [requested]
	requested = [w for w in requested if w]
	if not requested:
		frappe.throw(_("Select at least one worker to board."))

	manifest = boarding._trip_manifest_workers(trip.get("transport_request"))  # read-only reuse
	log = boarding._get_or_create_log(dispatch_trip)  # read-only reuse; draft TSL

	boarded, skipped = [], []
	for worker in requested:
		if worker not in manifest:
			# Off-manifest workers are audited as Wrong Trip, no boarding row.
			_log_manual_scan(dispatch_trip, trip, worker, "Wrong Trip", log.name,
			                  notes="Worker is not on this trip's manifest.")
			skipped.append({"worker": worker, "result": "Wrong Trip"})
			continue
		if boarding._already_boarded(log, worker):  # read-only reuse; idempotent
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
		log.save(ignore_permissions=True)  # audit-ok — driver resolved server-side, own trip
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
	doc.insert(ignore_permissions=True)  # audit-ok — manual board attempt is always recorded
	return doc.name

