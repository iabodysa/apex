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

# Roles that exclusively hold the authority to approve a payment or mark it
# paid. This is the core finance-boundary control.
_FINANCE_ROLES = {"Finance Manager", "System Manager"}

# Statuses whose entry requires finance authority.
_FINANCE_GATED_STATUSES = {"Approved by Finance", "Paid"}

# Known status values. The Select carries these for filtering/colour, but the
# Salis Payment Request Workflow owns the *transitions*.
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
		# The Select still carries the known states for filtering/colour, but the
		# Salis Payment Request Workflow owns *transitions* — this only rejects an
		# unknown value.
		if self.status and self.status not in VALID_STATUSES:
			frappe.throw(_("Invalid status: {0}").format(self.status))

		if not self.requested_by:
			self.requested_by = frappe.session.user
		self._set_financial_defaults()
		self._enforce_finance_gate()

	# Submit/cancel are recorded natively (Version track_changes + auto-comment).

	# ------------------------------------------------------------------ helpers

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

	def _old_status(self):
		previous = self.get_doc_before_save()
		# A brand-new document has no prior state; treat it as Draft.
		return (previous.status if previous else None) or "Draft"

	def _enforce_finance_gate(self):
		"""Finance-exclusive gate (kept as a hard server-side block; defence in
		depth alongside the workflow condition and the permission hook).

		Entering "Approved by Finance" or "Paid" is permitted ONLY when the
		current user holds a finance authority role and is not the requester.
		This step cannot be bypassed, even on a save that does not go through the
		workflow action. On entering "Approved by Finance", stamp the approver."""
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

		if new_status == "Approved by Finance":
			if not self.finance_approved_by:
				self.finance_approved_by = frappe.session.user
			if not self.finance_approved_on:
				self.finance_approved_on = now()
