"""Movement Cost Recovery controller.

Movement-domain control to recover losses (vehicle damage, fuel misuse,
custody loss, fines) with native-workflow authority and an audit trail.

Scope boundary: this DocType is Movement-domain only. It documents the
recovery and routes authorization through the native Movement Cost Recovery
Workflow (Fleet Manager / System Manager, no self-approval).
The actual salary deduction stays with Finance/HR and is handled via the
referenced Salis Payment Request; this controller posts NO General Ledger /
Journal / Payment Entry and never performs the deduction itself.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class MovementCostRecovery(Document):
	def validate(self):
		self._set_financial_defaults()
		if (self.amount or 0) <= 0:
			frappe.throw(_("Amount must be greater than zero."))
		if self.status == "Approved" and not self.basis_evidence:
			frappe.throw(_("Basis / Evidence is required before a recovery can be Approved."))

	def _set_financial_defaults(self):
		"""Default company and cost center from Salis Settings for reporting and
		financial context. Reference fields only - no GL/Payment Entry is posted."""
		from apex_habitat.apex_core.doctype.salis_settings.salis_settings import (
			get_default_company,
			get_default_cost_center,
		)

		if not self.company:
			self.company = get_default_company()
		if not self.cost_center:
			self.cost_center = get_default_cost_center()

	# Authorization is routed through the native Movement Cost Recovery Workflow:
	# only Fleet Manager / System Manager can drive Approve/Recover/Waive, and the
	# Approve transition forbids self-approval (allow_self_approval=0). Submit/cancel
	# are recorded natively (Version track_changes + auto-comment).
