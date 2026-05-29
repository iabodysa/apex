"""Salis Payment Request controller.

Enforces the finance boundary: every payable item routes
through a Finance-exclusive approval gate, and Finance cannot be bypassed.

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

# Terminal statuses - no further transition is allowed out of them.
_TERMINAL_STATUSES = {"Paid", "Rejected", "Cancelled"}

# Allowed forward status transitions. A status may always remain unchanged.
# Any non-terminal status may move to Rejected or Cancelled.
_ALLOWED_TRANSITIONS = {
	"Draft": {"Pending Finance", "Rejected", "Cancelled"},
	"Pending Finance": {"Approved by Finance", "Rejected", "Cancelled"},
	"Approved by Finance": {"Paid", "Rejected", "Cancelled"},
	"Paid": set(),
	"Rejected": set(),
	"Cancelled": set(),
}


class SalisPaymentRequest(Document):
	def before_insert(self):
		if not self.requested_by:
			self.requested_by = frappe.session.user

	def validate(self):
		if not self.requested_by:
			self.requested_by = frappe.session.user
		self._set_financial_defaults()
		self._enforce_status_flow()
		self._enforce_finance_gate()

	# Submit/cancel are recorded natively (Version track_changes + auto-comment).

	# ------------------------------------------------------------------ helpers

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

	def _old_status(self):
		previous = self.get_doc_before_save()
		# A brand-new document has no prior state; treat it as Draft.
		return (previous.status if previous else None) or "Draft"

	def _enforce_status_flow(self):
		"""Reject illegal status jumps (e.g. Draft -> Approved by Finance / Paid)."""
		new_status = self.status or "Draft"
		old_status = self._old_status()

		if new_status == old_status:
			return

		allowed = _ALLOWED_TRANSITIONS.get(old_status, set())
		if new_status not in allowed:
			frappe.throw(
				_("Cannot change Payment Request status from {0} to {1}.").format(
					_(old_status), _(new_status)
				)
			)

	def _enforce_finance_gate(self):
		"""Finance-exclusive gate.

		Entering "Approved by Finance" or "Paid" is permitted ONLY when the
		current user holds a finance authority role. This step cannot be
		bypassed. On entering "Approved by Finance", stamp the approver."""
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
