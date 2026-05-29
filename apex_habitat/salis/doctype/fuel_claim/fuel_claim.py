"""Fuel Claim controller.

Submittable Movement fuel claim and reconciliation against a Fuel Quota.
Movement is a service provider: Operations submits the
claim, Movement reconciles it against the internal Fuel Consumption Ledger.

The controller derives consumed litres from the ledger (sum of litres for the
claim's vehicle + period), computes the claimed-vs-consumed variance, enforces
a Draft -> Submitted to Movement -> Reconciled -> Approved (with Disputed /
Closed exits) status flow, and applies a Decentralized-of-Authority gate on
submit. A quota-increase claim or a large variance (> 10% of claimed litres)
demands the higher Operations tier and a Finance consult note; routine claims
settle at the Regional tier.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import ensure_approval

# Fraction of claimed litres above which a variance is treated as "large" and
# escalated to the Operations tier (with a Finance consult note).
LARGE_VARIANCE_RATIO = 0.1

# Allowed forward status transitions. A status may always remain unchanged.
_ALLOWED_TRANSITIONS = {
	"Draft": {"Submitted to Movement", "Disputed", "Closed"},
	"Submitted to Movement": {"Reconciled", "Disputed", "Closed"},
	"Reconciled": {"Approved", "Disputed", "Closed"},
	"Approved": {"Closed", "Disputed"},
	"Disputed": {"Submitted to Movement", "Reconciled", "Closed"},
	"Closed": set(),
}


class FuelClaim(Document):
	def before_insert(self):
		# Stamp the requester server-side (read-only field) so the
		# segregation-of-duties / maker-checker gate cannot be spoofed.
		if not self.requested_by:
			self.requested_by = frappe.session.user

	def validate(self):
		if not self.requested_by:
			self.requested_by = frappe.session.user
		if (self.claimed_litres or 0) <= 0:
			frappe.throw(_("Claimed Litres must be greater than zero."))
		self._set_financial_defaults()
		self._compute_consumption()
		self._enforce_status_flow()

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

	def before_submit(self):
		ensure_approval("Fuel Claim", self.name, required_tier=self._required_tier())

	# Submit/cancel are recorded natively (Version track_changes + auto-comment).

	# ------------------------------------------------------------------ helpers

	def _compute_consumption(self):
		"""Derive consumed litres from the Fuel Consumption Ledger and the
		claimed-vs-consumed variance. Consumed litres is the sum of ledger
		litres for this claim's vehicle and period."""
		consumed = 0.0
		if self.vehicle and self.period_month:
			rows = frappe.get_all(
				"Fuel Consumption Ledger",
				filters={"vehicle": self.vehicle, "period_month": self.period_month},
				fields=["litres"],
			)
			consumed = sum((row.litres or 0) for row in rows)

		self.consumed_litres = consumed
		self.variance_litres = (self.claimed_litres or 0) - consumed

	def _enforce_status_flow(self):
		"""Reject illegal status jumps (e.g. Draft -> Approved, Closed -> Draft)."""
		new_status = self.status or "Draft"
		previous = self.get_doc_before_save()
		old_status = (previous.status if previous else None) or "Draft"

		if new_status == old_status:
			return

		allowed = _ALLOWED_TRANSITIONS.get(old_status, set())
		if new_status not in allowed:
			frappe.throw(
				_("Cannot change Fuel Claim status from {0} to {1}.").format(
					_(old_status), _(new_status)
				)
			)

	def _is_large_variance(self):
		"""True when the absolute variance exceeds the configured fraction of the
		claimed litres (reconciliation tolerance)."""
		claimed = self.claimed_litres or 0
		if claimed <= 0:
			return False
		return abs(self.variance_litres or 0) > (LARGE_VARIANCE_RATIO * claimed)

	def _required_tier(self):
		"""Compute the authority tier this claim demands.

		A higher tier is required when scope crosses a threshold:
		a quota-increase claim or a large variance needs the higher Operations
		tier (and a Finance consult); routine claims settle at the Regional
		tier."""
		if self.is_increase or self._is_large_variance():
			return "Operations"
		return "Regional"
