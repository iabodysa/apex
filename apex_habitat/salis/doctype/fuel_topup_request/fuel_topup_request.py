"""Fuel Topup Request controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class FuelTopupRequest(Document):
	def validate(self):
		self._warn_overdue_temporary()

	def _warn_overdue_temporary(self):
		if not self.is_temporary or self.reverted:
			return
		if self.revert_due_date and getdate(self.revert_due_date) < getdate(nowdate()):
			frappe.msgprint(
				_(
					"This temporary top-up is past its revert due date ({0}) and has not been reverted."
				).format(self.revert_due_date),
				indicator="red",
				title=_("Temporary Top-up Not Reverted"),
			)
