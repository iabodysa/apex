# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver Portal — home endpoints (split from the driver_portal god module in P-180). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe

from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
    _label_trips,
    _attach_trip_maps,
    _today_attendance_state,
    _bound_vehicle,
    _license_countdown,
)


# [#jdcim7]
_OPEN_CLEARANCE_STATUSES = ("Open", "In Progress", "Blocked")



def _next_trip_today(driver):
	"""The driver's next actionable Dispatch Trip today, or None.

	"Next" is the earliest-departing trip that is not yet Completed/Cancelled.
	Route/vehicle link ids are swapped for their human labels (same as
	``my_trips_today``), and the trip's Trip Start Log state is attached so the
	portal can show whether execution has started without a second round-trip."""
	trips = frappe.get_all(
		"Dispatch Trip",
		filters={
			"driver": driver,
			"trip_date": frappe.utils.today(),
			"status": ["not in", ("Completed", "Cancelled")],
		},
		fields=["name", "route_plan", "vehicle", "depart_time", "return_time", "status"],
		order_by="depart_time asc",
		limit=1,
	)
	if not trips:
		return None
	trip = trips[0]
	_attach_trip_maps([trip])  # [#c8i03i]
	_label_trips([trip])
	log = frappe.db.get_value(
		"Trip Start Log",
		{"dispatch_trip": trip["name"], "driver": driver, "docstatus": ["<", 2]},
		["status", "start_datetime"],
		as_dict=True,
	)
	trip["started"] = bool(log)
	trip["trip_log_status"] = log.get("status") if log else None
	trip["start_datetime"] = (
		frappe.utils.cstr(log["start_datetime"]) if log and log.get("start_datetime") else None
	)
	return trip



@frappe.whitelist()
def get_my_today():
	"""One composite "today" payload for the driver Home screen (read).

	Identity-scoped: the driver is resolved from the session, never client-supplied.
	Collapses what the Home screen otherwise stitches from several endpoints into a
	single read so the dashboard paints in one round-trip:

	* ``attendance``      — today's attendance state (see ``_today_attendance_state``)
	* ``next_trip``       — the next not-done Dispatch Trip today (labelled, with its
	                        Trip Start Log state), or null
	* ``license``         — licence expiry + server-computed countdown/state
	* ``vehicle_bound``   — the driver has a vehicle bound (current or active assignment)
	* ``open_clearance``  — an exit clearance is still unresolved for the driver

	Read-only, no commit. Blocked (403) when the portal is disabled or the caller is
	not a linked driver."""
	_require_enabled()
	driver = _resolve_driver()
	return {
		"attendance": _today_attendance_state(driver),
		"next_trip": _next_trip_today(driver),
		"license": _license_countdown(driver),
		"vehicle_bound": bool(_bound_vehicle(driver)),
		"open_clearance": bool(
			frappe.db.exists(
				"Driver Clearance",
				{
					"driver": driver,
					"status": ["in", _OPEN_CLEARANCE_STATUSES],
					"docstatus": ["<", 2],
				},
			)
		),
	}

