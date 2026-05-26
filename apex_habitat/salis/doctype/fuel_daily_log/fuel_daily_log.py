"""Fuel Daily Log controller.

Non-submittable daily fuel consumption record. Light validation; an audit entry
is written once on creation (the doc is not submittable, so there is no submit
event to hook).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import log_activity


class FuelDailyLog(Document):
	def validate(self):
		if self.litres is not None and self.litres < 0:
			frappe.throw(_("Litres cannot be negative."))
		if self.odometer is not None and self.odometer < 0:
			frappe.throw(_("Odometer cannot be negative."))

	def after_insert(self):
		log_activity(
			action="Fuel Daily Log Recorded",
			entity_type="Salis Vehicle",
			entity_name=self.vehicle,
			details={"fuel_daily_log": self.name, "litres": self.litres, "amount": self.amount},
		)
