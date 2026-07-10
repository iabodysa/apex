# Copyright (c) 2026, AFMCO and contributors
"""Fuel Quota controller.

Submittable monthly fuel allocation. Consumption is posted by Fuel Request;
this controller validates allocation sanity and records an audit entry on submit.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from apex.salis.utils import lock_vehicle


class FuelQuota(Document):
	def validate(self):
		self._guard_duplicate()
		# An allocation of zero or negative litres is not a quota — reject it.
		if flt(self.monthly_litres) <= 0:
			frappe.throw(_("Monthly litres must be greater than zero."))
		monthly = self.monthly_litres or 0
		consumed = self.consumed_litres or 0
		if monthly and consumed > monthly:
			frappe.msgprint(
				_("Consumed litres ({0}) exceed the monthly quota ({1}).").format(
					consumed, monthly
				),
				indicator="orange",
				title=_("Quota Exceeded"),
			)

	def _guard_duplicate(self):
		"""One live quota per vehicle per period — a second (vehicle, period_month)
		would double-allocate the same month. Scoped to docstatus < 2 so a
		cancelled quota can be re-issued and an amendment of this same doc passes."""
		if not (self.vehicle and self.period_month):
			return
		# Serialize concurrent creates for the same vehicle: without this lock two
		# transactions both pass the exists-check below and double-allocate the month.
		lock_vehicle(self.vehicle)
		dup = frappe.db.exists(
			"Fuel Quota",
			{
				"vehicle": self.vehicle,
				"period_month": self.period_month,
				"docstatus": ["<", 2],
				"name": ["!=", self.name or ""],
			},
		)
		if dup:
			frappe.throw(
				_("Fuel Quota {0} already exists for vehicle {1} in period {2}.").format(
					dup, self.vehicle, self.period_month
				)
			)


def on_doctype_update():
	"""Belt-and-suspenders: a composite DB-level unique index prevents any duplicate
	that slips past the application-layer guard (e.g. direct DB inserts or a race
	that bypasses validate). Applied once at migrate/patch time.

	``docstatus`` is part of the key because Fuel Quota is submittable and the
	app guard is scoped to docstatus < 2: a Cancelled(2) quota may be re-issued
	and an amendment creates a new (vehicle, period_month) row alongside the
	cancelled original. A bare two-column index would reject those legitimate
	flows with DuplicateEntryError; including docstatus lets a Cancelled row
	coexist while still blocking a duplicate live quota (mirrors the Scheduled
	Task Instance backstop)."""
	frappe.db.add_unique(
		"Fuel Quota",
		["vehicle", "period_month", "docstatus"],
		constraint_name="uq_fuel_quota_vehicle_period",
	)
	# [#qzsfcl]
