"""Movement Cost Transfer controller.

Inter-project cost-transfer control for Movement costs.
Records the reallocation of a Movement-related cost (fuel, rental, trip cost,
other) from one project / cost center to another. Because crossing a project
boundary always demands Operations-tier authority, ``before_submit`` enforces a
Decentralized-of-Authority approval gate at the Operations tier.

NO-GL BOUNDARY
--------------
This DocType is an operational memo only. The "Posted (memo)" status records
that the transfer has been operationally acknowledged, but it does NOT write any
General Ledger or Journal Entry, and it does NOT touch any financial posting.
Financial reconciliation, if required, is handled outside this control by
Finance. Do not add GL/Journal-Entry posting here without explicit human
approval (it would change the financial-posting boundary - a major change per
project version discipline).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import ensure_approval, log_activity


class MovementCostTransfer(Document):
	def validate(self):
		self._validate_distinct_targets()
		self._stamp_approver()

	def before_submit(self):
		# Crossing a project boundary always requires Operations-tier authority.
		ensure_approval(
			"Movement Cost Transfer", self.name, required_tier="Operations"
		)

	def on_submit(self):
		log_activity(
			action="Movement Cost Transfer Submitted",
			entity_type="Movement Cost Transfer",
			entity_name=self.name,
			details={
				"transfer_type": self.transfer_type,
				"from_project": self.from_project,
				"to_project": self.to_project,
				"amount": self.amount,
			},
		)

	# ------------------------------------------------------------------ helpers

	def _validate_distinct_targets(self):
		"""A transfer must move cost between two different projects, and between
		two different cost centers when both are set."""
		if self.from_project and self.to_project and self.from_project == self.to_project:
			frappe.throw(
				_("From Project and To Project must be different for a cost transfer.")
			)

		if (
			self.from_cost_center
			and self.to_cost_center
			and self.from_cost_center == self.to_cost_center
		):
			frappe.throw(
				_("From Cost Center and To Cost Center must be different when both are set.")
			)

	def _stamp_approver(self):
		if self.status == "Approved" and not self.approved_by:
			self.approved_by = frappe.session.user
