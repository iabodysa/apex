"""Fuel Exception Case controller.

Submittable control record for disputed or suspicious fuel-control cases.
Holds usage/GPS evidence, requires evidence before a case may be resolved, and
enforces non-raiser resolution (segregation of duties — the user who raised the
case may not be the user who resolves it). Submit authority is owned by the
native **Fuel Exception Case Workflow**.

Status transitions are owned by the native **Fuel Exception Case Workflow** (see
``salis/workflow/fuel_exception_case_workflow/``), not by this controller. The
investigation states (Open -> Under Investigation -> Evidence Required) are
pre-submit; the document is submitted (docstatus 0 -> 1) by the ``Resolve`` or
``Reject`` transition (restricted to ``Fleet Manager``, with the Resolve
transition also carrying ``allow_self_approval=0``); ``Closed`` is the
post-submit terminal, reached from ``Resolved`` / ``Rejected`` as a docstatus-1
update (it finalizes, not voids, the case). The ``Resolve`` transition carries
the Segregation-of-Duties gate (``allow_self_approval=0`` +
``reported_by != session.user``) so the raiser can never resolve their own case.
The state field is ``allow_on_submit`` so a post-submit transition can move the
status.

This controller keeps only what the workflow cannot express: the reporter stamp
the SoD gate relies on, the evidence-before-resolution requirement plus the
non-raiser closer stamp/guard (defence in depth alongside the workflow
condition), and the initial-status guard (a case must be created at Open).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

# Known status values. The Select carries these for filtering / colour, but the
# Fuel Exception Case Workflow owns the *transitions* (which status is reachable
# from which, by whom). This controller only rejects an unknown value and pins
# the initial status to Open.
VALID_STATUSES = (
	"Open",
	"Under Investigation",
	"Evidence Required",
	"Resolved",
	"Rejected",
	"Closed",
)

# Closing states that require captured evidence and a distinct closer. The
# evidence/non-raiser gate fires on validate (i.e. on the Resolve transition,
# which submits the case). Closed is reached post-submit via the workflow's
# cancel transition, where validate does not run, so the practical enforcement
# point is Resolved; Closed is kept here as defence in depth for any non-cancel
# path that lands the document in Closed.
_CLOSING_STATUSES = {"Resolved", "Closed"}


class FuelExceptionCase(Document):
	def before_insert(self):
		self._default_reporter()

	def validate(self):
		self._default_reporter()
		if self.status and self.status not in VALID_STATUSES:
			frappe.throw(_("Invalid status: {0}").format(self.status))
		self._guard_initial_status()
		self._enforce_closure_controls()

	# Submit/cancel are driven by the native Fuel Exception Case Workflow (the
	# Resolve/Reject transitions perform docstatus 0 -> 1, restricted to Fleet
	# Manager with allow_self_approval=0). Submit/cancel are recorded natively
	# (Version track_changes + auto-comment).

	# ------------------------------------------------------------------ helpers

	def _default_reporter(self):
		"""Default the raiser to the current session user when blank."""
		if not self.reported_by:
			self.reported_by = frappe.session.user

	def _guard_initial_status(self):
		"""A new case must be created at the initial state (Open). Later states are
		reached only through the Fuel Exception Case Workflow, which the desk
		drives — this closes the insert-bypass the workflow itself cannot cover (a
		brand-new document inserted directly at a later/terminal status)."""
		if self.is_new() and self.status and self.status != "Open":
			frappe.throw(
				_("A Fuel Exception Case must be created with status Open; {0} is reached through the workflow.").format(
					_(self.status)
				)
			)

	def _enforce_closure_controls(self):
		"""Require evidence before resolution and enforce non-raiser resolution (segregation of duties)."""
		if self.status not in _CLOSING_STATUSES:
			return

		if not (self.evidence or self.evidence_notes):
			frappe.throw(_("Evidence required before resolving"))

		self.closed_by = frappe.session.user
		if self.closed_by == self.reported_by:
			frappe.throw(_("The closer must differ from the person who raised the case."))
