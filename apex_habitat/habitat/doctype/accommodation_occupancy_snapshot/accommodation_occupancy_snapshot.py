# Copyright (c) 2026, AFMCO Support Services and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AccommodationOccupancySnapshot(Document):
	pass


def on_doctype_update():
	"""Hard idempotency backstop: a composite UNIQUE index on ``(building,
	snapshot_date)`` so the daily one-row-per-building-per-day snapshot cannot be
	double-posted at the DB level even if ``habitat.tasks.daily_occupancy_snapshot``'s
	check-then-insert is bypassed by a race. Mirrors that job's
	``frappe.db.exists({building, snapshot_date})`` guard exactly. Guarded so
	pre-existing duplicate data logs rather than aborting migrate."""
	from apex_habitat.habitat.utils.ledger_index import add_unique_guarded

	add_unique_guarded(
		"Accommodation Occupancy Snapshot",
		["building", "snapshot_date"],
		constraint_name="unique_acc_occ_building_date",
	)
