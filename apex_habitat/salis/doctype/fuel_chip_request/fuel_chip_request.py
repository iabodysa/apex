"""Fuel Chip Request controller.

Submittable request to issue, replace, or cancel a vehicle fuel chip. Light
validation plus an audit entry on submit.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import add_timeline_note


class FuelChipRequest(Document):
	def validate(self):
		if self.action in ("Replace", "Cancel") and not self.chip_number:
			frappe.throw(
				_("A chip number is required to {0} a fuel chip.").format(_(self.action))
			)

	def before_submit(self):
		if self.action == "Cancel":
			if not self.inactivity_evidence:
				frappe.throw(
					_("Inactivity evidence is required to submit a fuel chip cancellation.")
				)
			if not self.owner_acknowledged:
				frappe.throw(
					_("Owner acknowledgement is required to submit a fuel chip cancellation.")
				)

	def on_submit(self):
		add_timeline_note(
			"Salis Vehicle",
			self.vehicle,
			_("Fuel chip {0} via request {1} (chip {2}).").format(
				_(self.action), self.name, self.chip_number or _("n/a")
			),
		)
