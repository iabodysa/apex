# Copyright (c) 2026, AFMCO Support Services and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VehicleUtilisationSnapshot(Document):
	pass


def on_doctype_update():
	"""Hard idempotency backstop: a composite UNIQUE index on (vehicle,
	snapshot_date) so the weekly one-row-per-vehicle-per-date snapshot cannot be
	double-posted at the DB level even if the engine's check-then-insert is
	bypassed by a race. Created/kept in sync on migrate via Frappe's
	on_doctype_update hook."""
	frappe.db.add_unique(
		"Vehicle Utilisation Snapshot",
		["vehicle", "snapshot_date"],
		constraint_name="unique_vus_vehicle_date",
	)
