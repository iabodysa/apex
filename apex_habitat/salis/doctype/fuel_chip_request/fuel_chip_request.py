"""Fuel Chip Request controller.

Submittable request to issue, replace, or cancel a vehicle fuel chip. Light
validation plus an audit entry on submit.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import log_activity


class FuelChipRequest(Document):
	def validate(self):
		if self.action in ("Replace", "Cancel") and not self.chip_number:
			frappe.throw(
				_("A chip number is required to {0} a fuel chip.").format(_(self.action))
			)

	def on_submit(self):
		log_activity(
			action="Fuel Chip {0}".format(self.action),
			entity_type="Salis Vehicle",
			entity_name=self.vehicle,
			details={"fuel_chip_request": self.name, "chip_number": self.chip_number},
		)
