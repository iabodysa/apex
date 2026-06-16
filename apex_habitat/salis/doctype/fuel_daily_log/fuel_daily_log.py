"""Fuel Daily Log controller.

Non-submittable daily fuel consumption record. Light validation; an audit entry
is written once on creation (the doc is not submittable, so there is no submit
event to hook).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.utils import add_timeline_note


class FuelDailyLog(Document):
	def validate(self):
		if self.litres is not None and self.litres < 0:
			frappe.throw(_("Litres cannot be negative."))
		if self.odometer is not None and self.odometer < 0:
			frappe.throw(_("Odometer cannot be negative."))

	def after_insert(self):
		add_timeline_note(
			"Salis Vehicle",
			self.vehicle,
			_("Fuel daily log {0}: {1} L, {2} SAR.").format(
				self.name, self.litres, self.amount
			),
		)

	def on_trash(self):
		# [#20djvr]
		# [#qdv2z9]
		# [#l8tkzu]
		# [#iuum6r]
		# [#ntgwmq]
		from apex_habitat.salis.fuel_engine import reverse_fuel_ledger

		reverse_fuel_ledger("Fuel Daily Log", self.name)
