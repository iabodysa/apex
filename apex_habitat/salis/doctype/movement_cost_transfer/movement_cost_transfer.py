"""Movement Cost Transfer controller.

Inter-project cost-transfer control for Movement costs.
Records the reallocation of a Movement-related cost (fuel, rental, trip cost,
other) from one project / cost center to another. Because crossing a project
boundary always demands Operations-tier authority, approval is governed by the
native Frappe "Movement Cost Transfer Workflow": the Approve / Reject
transitions out of "Pending Approval" are restricted to the Operations-tier
roles (Fleet Manager, System Manager), reproducing the former
required_tier="Operations" gate.

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


class MovementCostTransfer(Document):
	def validate(self):
		self._set_company_default()
		self._validate_distinct_targets()
		self._stamp_approver()

	def _set_company_default(self):
		"""Default the owning company from Salis Settings for reporting and
		financial context. Reference field only - this memo posts no GL."""
		if not self.company:
			from apex_habitat.apex_core.doctype.salis_settings.salis_settings import (
				get_default_company,
			)

			self.company = get_default_company()

	# Crossing a project boundary requires Operations-tier authority; that gate
	# is now enforced declaratively by the native "Movement Cost Transfer
	# Workflow" (Approve / Reject restricted to Fleet Manager / System Manager),
	# so no before_submit hook is needed here. Submit is recorded natively
	# (Version track_changes + auto-comment).

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
