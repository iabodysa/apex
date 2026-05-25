"""Fuel Request controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class FuelRequest(Document):
	def validate(self):
		self._enforce_status_flow()
		self._stamp_approver()

	def _enforce_status_flow(self):
		status = self.status or "Pending"
		previous = self.get_doc_before_save()
		previous_status = previous.status if previous else "Pending"

		# A request must be Approved before it can be marked Done.
		if status == "Done" and previous_status not in ("Approved", "Done"):
			frappe.throw(
				_("A Fuel Request must be Approved before it can be marked Done.")
			)

	def _stamp_approver(self):
		if self.status == "Approved" and not self.approved_by:
			self.approved_by = frappe.session.user
