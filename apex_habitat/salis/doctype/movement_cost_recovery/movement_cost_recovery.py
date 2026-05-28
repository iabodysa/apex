"""Movement Cost Recovery controller.

Movement-domain control to recover losses (vehicle damage, fuel misuse,
custody loss, fines) with tiered authority and an audit trail.

Scope boundary: this DocType is Movement-domain only. It documents the
recovery and routes authorization through the Delegation-of-Authority gate.
The actual salary deduction stays with Finance/HR and is handled via the
referenced Salis Payment Request; this controller posts NO General Ledger /
Journal / Payment Entry and never performs the deduction itself.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import ensure_approval, log_activity

# Amount (SAR) at or above which the recovery escalates to Operations-tier
# authority; below it, Regional tier suffices.
_OPERATIONS_TIER_THRESHOLD = 1000


class MovementCostRecovery(Document):
	def validate(self):
		if (self.amount or 0) <= 0:
			frappe.throw(_("Amount must be greater than zero."))
		if self.status == "Approved" and not self.basis_evidence:
			frappe.throw(_("Basis / Evidence is required before a recovery can be Approved."))

	def before_submit(self):
		required_tier = "Operations" if (self.amount or 0) >= _OPERATIONS_TIER_THRESHOLD else "Regional"
		ensure_approval("Movement Cost Recovery", self.name, required_tier=required_tier)

	def on_submit(self):
		log_activity(
			action="Cost Recovery Submitted",
			entity_type="Movement Cost Recovery",
			entity_name=self.name,
			details={
				"recovery_type": self.recovery_type,
				"amount": self.amount,
				"status": self.status,
			},
		)

	def on_cancel(self):
		log_activity(
			action="Cost Recovery Cancelled",
			entity_type="Movement Cost Recovery",
			entity_name=self.name,
			details={"recovery_type": self.recovery_type, "amount": self.amount},
		)
