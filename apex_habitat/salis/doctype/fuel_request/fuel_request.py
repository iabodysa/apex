"""Fuel Request controller (unified).

A single submittable fuel request whose ``request_type`` selects one of three
behaviours, preserving the contract of the three former DocTypes verbatim:

* **Standard** — fuel-increase request against a Fuel Quota. Drives a
  Pending -> Approved -> Done flow (Failed / Cancelled exits), enforces the
  Delegation-of-Authority approval gate, and posts/reverses quota consumption
  idempotently on submit/cancel. The Fuel accrual engine later ledgers the Done
  request (``ledgered`` flag) into the Fuel Consumption Ledger.
* **Top-up** — fuel top-up. Temporary top-ups carry a revert-due date and are
  auto-reverted by the daily Salis scheduler once overdue; this controller only
  surfaces a warning for the overdue case and guards status transitions.
* **Chip** — request to issue / replace / cancel a vehicle fuel chip. Light
  validation plus an audit entry on submit; a cancellation requires inactivity
  evidence and owner acknowledgement.

No GL is written.

Status transitions are owned by the native **Fuel Request Workflow** (see
``salis/workflow/fuel_request_workflow/``), not by this controller. The workflow
enforces the role per transition, the Segregation-of-Duties gate on the
approval (``allow_self_approval=0`` + ``requested_by != session.user``), and the
type-aware availability of the terminal transitions (``Mark Failed`` only for a
Standard request, ``Revert`` only for a Top-up) via its transition
``condition``s. The document is submitted (docstatus 0 -> 1) by the ``Approve``
transition; ``Done`` / ``Failed`` / ``Reverted`` are then reachable post-submit
(the state field is ``allow_on_submit``).

This controller keeps only what the workflow cannot express: the per-type
required-field validation, the Delegation-of-Authority approval gate
(``ensure_approval`` against an Approval Request + tier), the Chip
evidence/acknowledgement gate, the initial-status guard (a request must be
created at Pending), and the idempotent quota side-effects — Standard quota
consumption is applied when the request reaches Done (on submit if it submits
straight into Done, or on the post-submit transition into Done) and reversed on
cancel, guarded by the ``quota_applied`` flag.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from apex_habitat.salis.salis_lib import (
	add_timeline_note,
	ensure_approval,
	get_settings,
	lock_vehicle,
	tier_rank,
)

REQUEST_TYPES = ("Standard", "Top-up", "Chip")

# Known status values. The Select carries these for filtering / colour, but the
# Fuel Request Workflow owns the *transitions* (which status is reachable from
# which, by whom). This controller only rejects an unknown value and pins the
# initial status to Pending.
VALID_STATUSES = ("Pending", "Approved", "Done", "Failed", "Reverted", "Cancelled")


class FuelRequest(Document):
	# ------------------------------------------------------------------ lifecycle

	def before_insert(self):
		# Stamp the requester server-side (read-only field) so the workflow's
		# segregation-of-duties gate on the approval transition cannot be spoofed.
		if not self.requested_by:
			self.requested_by = frappe.session.user

	def validate(self):
		if not self.request_type:
			self.request_type = "Standard"
		if self.request_type not in REQUEST_TYPES:
			frappe.throw(_("Invalid Request Type: {0}").format(self.request_type))

		if self.status and self.status not in VALID_STATUSES:
			frappe.throw(_("Invalid status: {0}").format(self.status))
		if not self.requested_by:
			self.requested_by = frappe.session.user

		if self.request_type == "Standard":
			self._validate_standard()
		elif self.request_type == "Top-up":
			self._validate_topup()
		elif self.request_type == "Chip":
			self._validate_chip()

		self._guard_initial_status()
		self._stamp_approver()

	def before_submit(self):
		# Approval (DoA / SoD) gate applies to the litre-bearing types only; a
		# chip request carries its own evidence/acknowledgement gate instead.
		if self.request_type == "Standard":
			if self._needs_approval():
				ensure_approval(
					"Fuel Request", self.name, required_tier=self._required_tier()
				)
		elif self.request_type == "Top-up":
			if self._needs_approval():
				ensure_approval("Fuel Request", self.name)
		elif self.request_type == "Chip":
			self._guard_chip_cancellation()

	def on_submit(self):
		if self.request_type == "Standard":
			# The Approve transition submits the request at Approved; quota is
			# applied once it reaches Done (here if it submits straight into Done,
			# otherwise on the post-submit transition). Idempotent via quota_applied.
			if self.status == "Done":
				self._apply_quota_consumption()
		elif self.request_type == "Top-up":
			add_timeline_note(
				"Salis Vehicle",
				self.vehicle,
				_("Fuel top-up {0}: {1} L{2}.").format(
					self.name,
					self.topup_litres,
					_(" (temporary)") if self.is_temporary else "",
				),
			)
		elif self.request_type == "Chip":
			add_timeline_note(
				"Salis Vehicle",
				self.vehicle,
				_("Fuel chip {0} via request {1} (chip {2}).").format(
					_(self.action), self.name, self.chip_number or _("n/a")
				),
			)

	def on_update_after_submit(self):
		"""Fire the Done side-effect for a post-submit workflow transition.

		The Fuel Request Workflow submits at Approved (docstatus 0 -> 1) and then
		moves Approved -> Done as a post-submit transition (the state field is
		``allow_on_submit``). The Standard quota consumption must therefore post
		when the request *reaches* Done, not only at submit time. Idempotent via
		the ``quota_applied`` flag, so it is safe even if on_submit already ran."""
		if self.request_type == "Standard" and self.status == "Done":
			self._apply_quota_consumption()

	def on_cancel(self):
		if self.request_type == "Standard":
			self._reverse_quota_consumption()
		elif self.request_type == "Top-up":
			add_timeline_note(
				"Salis Vehicle",
				self.vehicle,
				_("Fuel top-up {0} cancelled ({1} L).").format(
					self.name, self.topup_litres
				),
			)

	# ------------------------------------------------------------------ per-type validation

	def _validate_standard(self):
		if (self.requested_litres or 0) <= 0:
			frappe.throw(_("Requested Litres must be greater than zero."))

	def _validate_topup(self):
		if (self.topup_litres or 0) <= 0:
			frappe.throw(_("Top-up Litres must be greater than zero."))
		if self.is_temporary and not self.revert_due_date:
			frappe.throw(_("A temporary top-up requires a revert due date."))
		self._warn_overdue_temporary()

	def _validate_chip(self):
		if not self.action:
			frappe.throw(_("A chip action (Issue / Replace / Cancel) is required."))
		if self.action in ("Replace", "Cancel") and not self.chip_number:
			frappe.throw(
				_("A chip number is required to {0} a fuel chip.").format(_(self.action))
			)

	# ------------------------------------------------------------------ status flow

	def _guard_initial_status(self):
		"""A new request must be created at the initial state (Pending). Later
		states are reached only through the Fuel Request Workflow, which the desk
		drives — this closes the insert-bypass the workflow itself cannot cover
		(a brand-new document inserted directly at a later/terminal status)."""
		if self.is_new() and self.status and self.status != "Pending":
			frappe.throw(
				_("A Fuel Request must be created with status Pending; {0} is reached through the workflow.").format(
					_(self.status)
				)
			)

	def _stamp_approver(self):
		if self.status == "Approved" and not self.approved_by:
			self.approved_by = frappe.session.user

	# ------------------------------------------------------------------ Top-up helpers

	def _warn_overdue_temporary(self):
		if not self.is_temporary or self.reverted:
			return
		if self.revert_due_date and getdate(self.revert_due_date) < getdate(nowdate()):
			frappe.msgprint(
				_(
					"This temporary top-up is past its revert due date ({0}) and has not been reverted."
				).format(self.revert_due_date),
				indicator="red",
				title=_("Temporary Top-up Not Reverted"),
			)

	# ------------------------------------------------------------------ Chip helpers

	def _guard_chip_cancellation(self):
		if self.action == "Cancel":
			if not self.inactivity_evidence:
				frappe.throw(
					_("Inactivity evidence is required to submit a fuel chip cancellation.")
				)
			if not self.owner_acknowledged:
				frappe.throw(
					_("Owner acknowledgement is required to submit a fuel chip cancellation.")
				)

	# ------------------------------------------------------------------ approval gate

	def _needs_approval(self):
		"""Approval is required when the requested volume exceeds the configured
		threshold, or when this is a cross-project request.

		The litre figure compared is the type-relevant one (Standard ->
		requested_litres, Top-up -> topup_litres). Cross-project escalation for a
		Standard request uses the linked quota's project; a Top-up uses the
		vehicle's project (it carries no quota), mirroring the two former
		controllers verbatim."""
		settings = get_settings()
		if not getattr(settings, "enable_approvals", 0):
			return False

		threshold = settings.fuel_request_approval_threshold_litres or 0
		if threshold and (self._litres() or 0) > threshold:
			return True

		if getattr(settings, "cross_project_needs_approval", 0) and self.project:
			if self.request_type == "Standard" and self.fuel_quota:
				quota_project = frappe.db.get_value("Fuel Quota", self.fuel_quota, "project")
				if quota_project and quota_project != self.project:
					return True
			elif self.request_type == "Top-up" and self.vehicle:
				vehicle_project = frappe.db.get_value("Salis Vehicle", self.vehicle, "project")
				if vehicle_project and vehicle_project != self.project:
					return True

		return False

	def _litres(self):
		"""The type-relevant litre figure for the approval threshold check."""
		if self.request_type == "Top-up":
			return self.topup_litres or 0
		return self.requested_litres or 0

	def _is_cross_project(self):
		"""True when a Standard request's project differs from its quota's project."""
		if not (self.project and self.fuel_quota):
			return False
		quota_project = frappe.db.get_value("Fuel Quota", self.fuel_quota, "project")
		return bool(quota_project and quota_project != self.project)

	def _required_tier(self):
		"""Compute the authority tier this (Standard) fuel request demands.

		Base tier is Project. The volume bands and the cross-project rule escalate
		it; the highest applicable tier wins. Thresholds are data-driven from
		Salis Settings, not hardcoded."""
		settings = get_settings()
		litres = self.requested_litres or 0
		ops_litres = settings.fuel_tier_operations_litres or 0
		reg_litres = settings.fuel_tier_regional_litres or 0

		tier = "Project"
		if ops_litres and litres >= ops_litres:
			tier = "Operations"
		elif reg_litres and litres >= reg_litres:
			tier = "Regional"

		if self._is_cross_project() and tier_rank(tier) < tier_rank("Regional"):
			tier = "Regional"

		return tier

	# ------------------------------------------------------------------ quota posting (Standard)

	def _apply_quota_consumption(self):
		"""Idempotently add requested_litres to the quota's consumed_litres."""
		if self.quota_applied or not self.fuel_quota:
			return

		lock_vehicle(self.vehicle)
		frappe.db.sql(
			"SELECT name FROM `tabFuel Quota` WHERE name=%s FOR UPDATE", self.fuel_quota
		)

		quota = frappe.db.get_value(
			"Fuel Quota", self.fuel_quota, ["consumed_litres", "monthly_litres", "status"], as_dict=True
		)
		if not quota:
			return

		new_consumed = (quota.consumed_litres or 0) + (self.requested_litres or 0)
		updates = {"consumed_litres": new_consumed}
		monthly = quota.monthly_litres or 0
		if monthly and new_consumed >= monthly and quota.status == "Active":
			updates["status"] = "Exhausted"
		frappe.db.set_value("Fuel Quota", self.fuel_quota, updates)

		self.db_set("quota_applied", 1)
		add_timeline_note(
			"Fuel Quota",
			self.fuel_quota,
			_("Consumed {0} L via Fuel Request {1}.").format(
				self.requested_litres, self.name
			),
		)

	def _reverse_quota_consumption(self):
		"""Reverse a previously applied quota consumption on cancel."""
		if not self.quota_applied or not self.fuel_quota:
			return

		lock_vehicle(self.vehicle)
		frappe.db.sql(
			"SELECT name FROM `tabFuel Quota` WHERE name=%s FOR UPDATE", self.fuel_quota
		)

		quota = frappe.db.get_value(
			"Fuel Quota", self.fuel_quota, ["consumed_litres", "monthly_litres", "status"], as_dict=True
		)
		if quota:
			new_consumed = max((quota.consumed_litres or 0) - (self.requested_litres or 0), 0)
			updates = {"consumed_litres": new_consumed}
			monthly = quota.monthly_litres or 0
			if quota.status == "Exhausted" and (not monthly or new_consumed < monthly):
				updates["status"] = "Active"
			frappe.db.set_value("Fuel Quota", self.fuel_quota, updates)

		self.db_set("quota_applied", 0)
		add_timeline_note(
			"Fuel Quota",
			self.fuel_quota,
			_("Reversed {0} L from Fuel Request {1}.").format(
				self.requested_litres, self.name
			),
		)
