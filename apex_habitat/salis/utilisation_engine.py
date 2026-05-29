# Copyright (c) 2026, AFMCO Support Services Co. Ltd and contributors
# For license information, please see license.txt

"""Vehicle Utilisation Snapshot engine.

Background engine (system-written, read-only, no-GL) mirroring the Habitat
daily occupancy snapshot pattern. Humans never enter these rows; the weekly
scheduler writes one point-in-time utilisation row per active vehicle so that
utilisation history/trends survive (the live fleet state keeps no history).
Reports and KPIs derive from the snapshots.
"""

import frappe
from frappe.utils import add_days, getdate, today

PERIOD_DAYS = 7


def weekly_vehicle_utilisation_snapshot() -> None:
	"""Write a weekly utilisation row per Active Salis Vehicle.

	Over the trailing 7 days, count Completed Dispatch Trips for the vehicle,
	derive idle days (days in the window with no completed trip), and compute
	utilisation as the share of days in the window that had at least one trip.
	Idempotent on vehicle + snapshot_date. One row per vehicle; per-row
	try/except so a single failure does not abort the run; no commit in loop.
	"""
	snapshot_date = today()
	window_start = add_days(snapshot_date, -(PERIOD_DAYS - 1))

	start = 0
	batch_size = 500
	while True:
		vehicle_names = frappe.get_all(
			"Salis Vehicle",
			filters={"status": "Active"},
			pluck="name",
			limit_start=start,
			limit_page_length=batch_size,
		)
		if not vehicle_names:
			break
		for vehicle_name in vehicle_names:
			try:
				if frappe.db.exists(
					"Vehicle Utilisation Snapshot",
					{"vehicle": vehicle_name, "snapshot_date": snapshot_date},
				):
					continue

				# Completed trips in the trailing window (Dispatch Trip is
				# submittable; a Completed trip is submitted, docstatus=1).
				trip_rows = frappe.get_all(
					"Dispatch Trip",
					filters={
						"vehicle": vehicle_name,
						"status": "Completed",
						"docstatus": 1,
						"trip_date": ["between", [window_start, snapshot_date]],
					},
					fields=["trip_date"],
				)
				trips_count = len(trip_rows)

				# Days in the window that had at least one completed trip.
				days_with_trip = len({getdate(r.trip_date) for r in trip_rows if r.trip_date})
				idle_days = max(PERIOD_DAYS - days_with_trip, 0)
				utilisation_pct = (
					round(days_with_trip / PERIOD_DAYS * 100, 2) if PERIOD_DAYS else 0.0
				)

				frappe.get_doc(
					{
						"doctype": "Vehicle Utilisation Snapshot",
						"snapshot_date": snapshot_date,
						"vehicle": vehicle_name,
						"period_days": PERIOD_DAYS,
						"trips_count": trips_count,
						"idle_days": idle_days,
						"utilisation_pct": utilisation_pct,
					}
				).insert(ignore_permissions=True)  # audit-ok
			except Exception:
				frappe.db.rollback()
				frappe.log_error(
					message=frappe.get_traceback(),
					title=f"Vehicle utilisation snapshot failed for {vehicle_name}"[:140],
				)
		start += batch_size

	frappe.logger().info("weekly_vehicle_utilisation_snapshot: snapshots written.")
