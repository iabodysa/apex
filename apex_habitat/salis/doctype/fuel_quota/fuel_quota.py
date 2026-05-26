"""Fuel Quota controller.

Submittable monthly fuel allocation. Consumption is posted by Fuel Request;
this controller validates allocation sanity and records an audit entry on submit.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import log_activity


class FuelQuota(Document):
	def validate(self):
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

	def on_submit(self):
		log_activity(
			action="Fuel Quota Allocated",
			entity_type="Fuel Quota",
			entity_name=self.name,
			details={
				"vehicle": self.vehicle,
				"period_month": self.period_month,
				"monthly_litres": self.monthly_litres,
			},
		)
