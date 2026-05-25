"""Fuel Quota controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


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
