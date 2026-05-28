"""Fuel Exception Case controller.

Submittable control record for disputed or suspicious fuel-control cases.
Holds usage/GPS evidence, enforces a status state
machine, requires evidence before a case may be resolved or closed, and
enforces non-raiser closure (segregation of duties — the user who raised the
case may not be the user who closes it). Submit is gated behind an
Operations-tier Approval Request.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import ensure_approval, log_activity

# Allowed forward status transitions. A status may always remain unchanged.
# Open -> Under Investigation -> Evidence Required -> Resolved/Rejected -> Closed.
# Rejected and Closed are reachable from the investigation states as exits.
_ALLOWED_TRANSITIONS = {
	"Open": {"Under Investigation", "Rejected", "Closed"},
	"Under Investigation": {"Evidence Required", "Resolved", "Rejected", "Closed"},
	"Evidence Required": {"Under Investigation", "Resolved", "Rejected", "Closed"},
	"Resolved": {"Closed", "Rejected"},
	"Rejected": {"Closed"},
	"Closed": set(),
}

# Terminal/closing states that require captured evidence and a distinct closer.
_CLOSING_STATUSES = {"Resolved", "Closed"}


class FuelExceptionCase(Document):
	def before_insert(self):
		self._default_reporter()

	def validate(self):
		self._default_reporter()
		self._enforce_status_flow()
		self._enforce_closure_controls()

	def before_submit(self):
		ensure_approval("Fuel Exception Case", self.name, required_tier="Operations")

	def on_submit(self):
		log_activity(
			action="Fuel Exception Case Submitted",
			entity_type="Fuel Exception Case",
			entity_name=self.name,
			details={"exception_type": self.exception_type, "status": self.status},
		)

	def on_cancel(self):
		log_activity(
			action="Fuel Exception Case Cancelled",
			entity_type="Fuel Exception Case",
			entity_name=self.name,
			details={"exception_type": self.exception_type, "status": self.status},
		)

	# ------------------------------------------------------------------ helpers

	def _default_reporter(self):
		"""Default the raiser to the current session user when blank."""
		if not self.reported_by:
			self.reported_by = frappe.session.user

	def _enforce_status_flow(self):
		"""Reject illegal status jumps."""
		new_status = self.status or "Open"
		previous = self.get_doc_before_save()
		old_status = (previous.status if previous else None) or "Open"

		if new_status == old_status:
			return

		allowed = _ALLOWED_TRANSITIONS.get(old_status, set())
		if new_status not in allowed:
			frappe.throw(
				_("Cannot change Fuel Exception Case status from {0} to {1}.").format(
					_(old_status), _(new_status)
				)
			)

	def _enforce_closure_controls(self):
		"""Require evidence before resolution/closure and enforce non-raiser closure (segregation of duties)."""
		if self.status not in _CLOSING_STATUSES:
			return

		if not (self.evidence or self.evidence_notes):
			frappe.throw(_("Evidence required before resolving"))

		self.closed_by = frappe.session.user
		if self.closed_by == self.reported_by:
			frappe.throw(_("The closer must differ from the person who raised the case."))
