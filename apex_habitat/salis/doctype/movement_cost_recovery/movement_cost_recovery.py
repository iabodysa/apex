# Copyright (c) 2026, AFMCO and contributors
"""Movement Cost Recovery controller.

Movement-domain control to recover losses (vehicle damage, fuel misuse,
custody loss, fines) with native-workflow authority and an audit trail.

Scope boundary: this DocType is Movement-domain only. It documents the
recovery and routes authorization through the native Movement Cost Recovery
Workflow (Fleet Manager / System Manager, no self-approval).
The actual salary deduction stays with Finance/HR and is handled via the
referenced Salis Payment Request; this controller posts NO General Ledger /
Journal / Payment Entry and never performs the deduction itself.

Delegation-of-Authority gate: ``amount`` is compared on save against the Cost
Recovery Operations Threshold (``cost_recovery_ops_threshold`` in Salis
Settings) to derive ``needs_operations``. The workflow's Regional-tier approve
(Fleet Supervisor) is gated off when that flag is set, so only the Operations
tier (Fleet Manager / System Manager) can approve a high-value recovery.
``_enforce_doa_gate`` is the hard, no-bypass server guard held in addition to the
workflow condition (defence in depth).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# [#mcr-ops] Operations tier may authorise a high-value (>= threshold) recovery.
_OPERATIONS_ROLES = {"Fleet Manager", "System Manager"}


class MovementCostRecovery(Document):
	def validate(self):
		self._set_financial_defaults()
		if (self.amount or 0) <= 0:
			frappe.throw(_("Amount must be greater than zero."))
		if self.status == "Approved" and not self.basis_evidence:
			frappe.throw(_("Basis / Evidence is required before a recovery can be Approved."))
		# The recovery cannot be authorised against a person until they have accepted
		# responsibility. The enforcement points are Approve (the submit) and Recover;
		# Acknowledged is the act of acknowledging, so it is not gated. Waive/Reject/Cancel
		# need no acknowledgement (a claim can be dropped without the party accepting it).
		if self.status in ("Approved", "Recovered") and not self.acknowledgement_received:
			frappe.throw(_("Acknowledgement Received must be set before a recovery can be {0}.").format(_(self.status)))
		self._derive_needs_operations()
		self._enforce_doa_gate()

	def _derive_needs_operations(self):
		"""Server-side DoA derivation: set ``needs_operations`` when the amount
		reaches the Cost Recovery Operations Threshold (read via the zero-trap
		helper). Derived here — never trusted from the client."""
		from apex_habitat.apex_core.doctype.salis_settings.salis_settings import get_salis_float

		threshold = get_salis_float("cost_recovery_ops_threshold", 1000.0)
		self.needs_operations = 1 if flt(self.amount) >= threshold else 0

	def _enforce_doa_gate(self):
		"""Hard, no-bypass DoA block (defence in depth alongside the workflow
		condition). When a recovery enters the Approved/Recovered state and it needs
		Operations authority, the approver must hold an Operations-tier role."""
		if self.status not in ("Approved", "Recovered") or not self.needs_operations:
			return
		if not (_OPERATIONS_ROLES & set(frappe.get_roles())):
			frappe.throw(
				_(
					"This recovery reaches the Operations threshold and can only be approved by Operations-tier authority (Fleet Manager)."
				)
			)

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

	# [#m7rmjl]
