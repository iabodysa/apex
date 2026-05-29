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

from apex_habitat.salis.salis_lib import ensure_approval

# Fallback amount (SAR) at or above which the recovery escalates to Operations-
# tier authority, used only when Salis Settings has no configured threshold;
# below it, Regional tier suffices.
_OPERATIONS_TIER_THRESHOLD_DEFAULT = 1000


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
		from apex_habitat.salis.doctype.salis_settings.salis_settings import (
			get_default_company,
			get_default_cost_center,
		)

		if not self.company:
			self.company = get_default_company()
		if not self.cost_center:
			self.cost_center = get_default_cost_center()

	def before_submit(self):
		# Threshold is configurable via Salis Settings so the SAR recovery gate can
		# be tuned without a code change; fall back to the default if unset.
		threshold = frappe.db.get_single_value(
			"Salis Settings", "cost_recovery_ops_threshold_sar"
		)
		if not threshold:
			threshold = _OPERATIONS_TIER_THRESHOLD_DEFAULT
		required_tier = "Operations" if (self.amount or 0) >= threshold else "Regional"
		ensure_approval("Movement Cost Recovery", self.name, required_tier=required_tier)

	# Submit/cancel are recorded natively (Version track_changes + auto-comment).
