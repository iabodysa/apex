"""Fuel Claim controller.

Submittable Movement fuel claim and reconciliation against a Fuel Quota.
Movement is a service provider: Operations submits the
claim, Movement reconciles it against the internal Fuel Consumption Ledger.

The controller derives consumed litres from the ledger (sum of litres for the
claim's vehicle + period), computes the claimed-vs-consumed variance, and
applies a Delegation-of-Authority gate on submit. A quota-increase claim or a
large variance (> 10% of claimed litres) demands the higher Operations tier and
a Finance consult note; routine claims settle at the Regional tier.

Status transitions are owned by the native **Fuel Claim Workflow** (see
``salis/workflow/fuel_claim_workflow/``), not by this controller. The workflow
enforces the role per transition and the Segregation-of-Duties gate on the
approval (``allow_self_approval=0`` + ``requested_by != session.user``). The
document is submitted (docstatus 0 -> 1) by the ``Approve`` transition (where the
Delegation-of-Authority gate in ``before_submit`` fires); ``Closed`` is the
post-submit terminal, reached from ``Approved`` as a docstatus-1 update (it
finalizes, not voids, the claim — there is no cancel side-effect). The state
field is ``allow_on_submit`` so a post-submit transition can move the status.

This controller keeps only what the workflow cannot express: the required-field
validation, the ledger-derived consumption/variance computation, the financial
reference defaults, the Delegation-of-Authority approval gate (``ensure_approval``
against an Approval Request + tier), the initial-status guard (a claim must be
created at Draft), and the server-side requester stamp the SoD gate relies on.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import ensure_approval

# Fraction of claimed litres above which a variance is treated as "large" and
# escalated to the Operations tier (with a Finance consult note).
LARGE_VARIANCE_RATIO = 0.1

# Known status values. The Select carries these for filtering / colour, but the
# Fuel Claim Workflow owns the *transitions* (which status is reachable from
# which, by whom). This controller only rejects an unknown value and pins the
# initial status to Draft.
VALID_STATUSES = (
	"Draft",
	"Submitted to Movement",
	"Reconciled",
	"Approved",
	"Disputed",
	"Closed",
)


class FuelClaim(Document):
	def before_insert(self):
		# Stamp the requester server-side (read-only field) so the
		# segregation-of-duties / maker-checker gate cannot be spoofed.
		if not self.requested_by:
			self.requested_by = frappe.session.user

	def validate(self):
		if not self.requested_by:
			self.requested_by = frappe.session.user
		if self.status and self.status not in VALID_STATUSES:
			frappe.throw(_("Invalid status: {0}").format(self.status))
		if (self.claimed_litres or 0) <= 0:
			frappe.throw(_("Claimed Litres must be greater than zero."))
		self._set_financial_defaults()
		self._compute_consumption()
		self._guard_initial_status()

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

	def _guard_initial_status(self):
		"""A new claim must be created at the initial state (Draft). Later states
		are reached only through the Fuel Claim Workflow, which the desk drives —
		this closes the insert-bypass the workflow itself cannot cover (a brand-new
		document inserted directly at a later/terminal status)."""
		if self.is_new() and self.status and self.status != "Draft":
			frappe.throw(
				_("A Fuel Claim must be created with status Draft; {0} is reached through the workflow.").format(
					_(self.status)
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
