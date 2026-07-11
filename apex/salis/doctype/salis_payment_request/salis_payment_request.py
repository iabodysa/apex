# Copyright (c) 2026, AFMCO and contributors
"""Salis Payment Request controller.

Enforces the finance boundary: every payable item routes
through a Finance-exclusive approval gate, and Finance cannot be bypassed.

Status transitions are owned by the native **Salis Payment Request Workflow**
(see ``salis/workflow/salis_payment_request_workflow/``), not by this
controller. The finance approval/payment transitions ("Approve (Finance)" and
"Mark Paid") are **Finance-Manager-only** and carry the Segregation-of-Duties
condition ``requested_by != session.user`` so the (server-stamped) requester can
never approve or pay their own request. The same maker != checker rule is also
held at the permission layer by ``permissions.payment_sod_has_permission`` —
both gates stand (defence in depth). This controller keeps the finance-gate
*data* guard ``_enforce_finance_gate`` (the no-bypass finance boundary and the
approver stamp) so any save that lands the document in a Finance-exclusive state
— including a path that bypasses the workflow action — is still blocked.

This DocType posts NO General Ledger / Journal / Payment Entry. It is a
payment request record only. ``linked_payment_entry`` is a reference-only
field set externally once Finance posts the actual payment in the accounting
module; this controller must never write accounting.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now

from apex.salis.utils import set_financial_defaults

# [#72wj77]
_FINANCE_ROLES = {"Finance Manager", "System Manager"}

# [#h4c606]
_FINANCE_GATED_STATUSES = {"Approved by Finance", "Paid"}

# [#j18gl5]
VALID_STATUSES = (
	"Draft",
	"Pending Finance",
	"Approved by Finance",
	"Paid",
	"Rejected",
	"Cancelled",
)


class SalisPaymentRequest(Document):
	def before_insert(self):
		if not self.requested_by:
			self.requested_by = frappe.session.user

	def validate(self):
		# [#3b4mlx]
		if self.status and self.status not in VALID_STATUSES:
			frappe.throw(_("Invalid status: {0}").format(self.status))

		if not self.requested_by:
			self.requested_by = frappe.session.user
		set_financial_defaults(self)
		# [#lme2on]
		if (self.amount or 0) <= 0:
			frappe.throw(_("Amount must be greater than zero."))
		# [#fyykgk]
		self._guard_finance_stamp()
		self._enforce_finance_gate()

	# [#hbyegp]

	# [#m88md8]

	def _old_status(self):
		previous = self.get_doc_before_save()
		# [#mp8kt3]
		return (previous.status if previous else None) or "Draft"

	def _guard_finance_stamp(self):
		"""The approver stamp is SERVER-OWNED: only ``_enforce_finance_gate`` may
		write ``finance_approved_by`` / ``finance_approved_on``, and only after the
		finance-role and SoD checks. ``read_only`` is a UI-only attribute (it is NOT
		enforced on save) and these fields sit at permlevel 0, so without this guard
		any role with create/write could forge the stamp directly - e.g. insert with
		a non-gated status, where the gate early-returns and never inspects it - and
		the payment router would then route a real payment off the forged value.
		Revert any caller-supplied value to the stored one so the stamp can never be
		introduced or altered on a save except by the gate itself."""
		before = self.get_doc_before_save()
		self.finance_approved_by = before.finance_approved_by if before else None
		self.finance_approved_on = before.finance_approved_on if before else None

	def _enforce_finance_gate(self):
		"""Finance-exclusive gate (kept as a hard server-side block; defence in
		depth alongside the workflow condition and the permission hook).

		Entering "Approved by Finance" or "Paid" is permitted ONLY when the
		current user holds a finance authority role and is not the requester.
		This step cannot be bypassed, even on a save that does not go through the
		workflow action. On entering any finance-gated state, stamp the approver."""
		new_status = self.status or "Draft"
		old_status = self._old_status()

		if new_status == old_status or new_status not in _FINANCE_GATED_STATUSES:
			return

		if not (_FINANCE_ROLES & set(frappe.get_roles())):
			frappe.throw(
				_("Only Finance can approve or mark a payment as paid. This step cannot be bypassed.")
			)

		if self.requested_by and frappe.session.user == self.requested_by:
			frappe.throw(
				_("You cannot approve or pay a Payment Request you raised; a different Finance approver is required.")
			)

		# [#fykrtv]
		if not self.finance_approved_by:
			self.finance_approved_by = frappe.session.user
		if not self.finance_approved_on:
			self.finance_approved_on = now()
