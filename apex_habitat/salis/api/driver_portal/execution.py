# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver Portal — execution endpoints (split from the driver_portal god module in P-180). Kernel helpers are imported from the package so the canonical dotted path apex_habitat.salis.api.driver_portal.<fn> is unchanged."""

import frappe
from frappe import _

from apex_habitat.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
    _resolve_my_trip,
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



@frappe.whitelist(methods=["POST"])
def start_my_trip(dispatch_trip):
	"""Mark the driver's own trip Started, creating its Trip Start Log (write).

	Identity-scoped: the driver is resolved from the session and the trip is honoured
	only when it belongs to that driver (``_resolve_my_trip``). Gets-or-creates the
	Trip Start Log for (trip, driver) and stamps ``start_datetime``; idempotent — a
	second tap returns the existing state rather than duplicating. The Driver holds an
	``if_owner`` DocPerm on Trip Start Log, and the write is server-authoritative
	(driver resolved from session), so ``ignore_permissions`` is set. No GL — Trip Start
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
		doc.insert(ignore_permissions=True)  # audit-ok — driver resolved server-side
	return _trip_log_state(driver, dispatch_trip)



@frappe.whitelist(methods=["POST"])
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
	doc.flags.ignore_permissions = True  # audit-ok — driver resolved from session identity
	doc.save() if not doc.is_new() else doc.insert()
	return _trip_log_state(driver, dispatch_trip)



@frappe.whitelist(methods=["POST"])
def push_driver_position(dispatch_trip, lat, lng):
	"""Record the driver's live GPS position onto their own Dispatch Trip (write).

	The driver portal calls this periodically while a trip is dispatched; the
	stored position feeds the worker's live ride ETA on Masar Home. Identity-scoped
	via ``_resolve_my_trip`` — a driver can only write a trip that belongs to them,
	so one driver can never spoof another driver's (or another trip's) position by
	passing an arbitrary id. Latitude/longitude are range-validated. The write is
	server-authoritative (driver resolved from the session), and the position fields
	are ``allow_on_submit`` on the submitted trip, so ``db_set`` persists without an
	amendment. No GL — this is an execution/telematics stamp only."""
	_require_enabled()
	driver = _resolve_driver()
	# Ownership guard: fail closed unless the trip is this driver's.
	_resolve_my_trip(dispatch_trip, driver)
	lat, lng = _validate_coords(lat, lng)
	now = frappe.utils.now_datetime()
	# db_set on the already-loaded doc keeps the write on the submitted trip (fields
	# are allow_on_submit) without triggering a full validate/amendment cycle.
	trip = frappe.get_doc("Dispatch Trip", dispatch_trip)
	trip.db_set(
		{"driver_lat": lat, "driver_lng": lng, "driver_position_updated_at": now},
		update_modified=False,
	)
	return {
		"dispatch_trip": dispatch_trip,
		"driver_lat": lat,
		"driver_lng": lng,
		"driver_position_updated_at": frappe.utils.cstr(now),
	}



def _validate_coords(lat, lng):
	"""Coerce ``lat``/``lng`` to floats and assert they are in valid WGS-84 ranges
	(lat -90..90, lng -180..180). A client-supplied position that is non-numeric or
	out of range is rejected so a bad reading can never corrupt the ETA math."""
	try:
		lat = float(lat)
		lng = float(lng)
	except (TypeError, ValueError):
		frappe.throw(_("A valid GPS position (latitude and longitude) is required."))
	if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lng <= 180.0):
		frappe.throw(_("The GPS position is outside the valid coordinate range."))
	return lat, lng



@frappe.whitelist(methods=["POST"])
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
	_resolve_my_trip(dispatch_trip, driver)  # enforces own-trip; raises if not
	log = _open_trip_log(dispatch_trip, driver)
	if not log:
		# A stop can only be marked on a started trip (stop state lives on the log).
		frappe.throw(_("Start the trip before marking stops."))

	done = frappe.utils.cint(done)
	existing = next((r for r in (log.stop_progress or []) if r.route_stop == route_stop), None)
	if existing:
		existing.done = done
		existing.done_at = frappe.utils.now_datetime() if done else None
	else:
		log.append(
			"stop_progress",
			{
				"route_stop": route_stop,
				"sequence": frappe.utils.cint(sequence) if sequence is not None else None,
				"stop_name": stop_name,
				"done": done,
				"done_at": frappe.utils.now_datetime() if done else None,
			},
		)
	log.flags.ignore_permissions = True  # audit-ok — driver resolved from session identity
	log.save()
	return {
		"route_stop": route_stop,
		"done": bool(done),
		"stop_progress": _stop_progress_map(dispatch_trip, driver),
	}

