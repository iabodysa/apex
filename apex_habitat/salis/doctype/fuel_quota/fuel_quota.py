"""Fuel Quota controller.

Submittable monthly fuel allocation. Consumption is posted by Fuel Request;
this controller validates allocation sanity and records an audit entry on submit.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.utils import lock_vehicle


class FuelQuota(Document):
	def validate(self):
		self._guard_duplicate()
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

	# [#qzsfcl]
