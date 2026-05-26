"""Fuel Request controller.

Submittable fuel-increase request against a Fuel Quota. Drives a
Pending -> Approved -> Done flow (with Failed / Cancelled exits), enforces a
Decentralized-of-Authority approval gate, and posts/reverses quota consumption
idempotently on submit/cancel.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import (
	ensure_approval,
	get_settings,
	lock_vehicle,
	log_activity,
	tier_rank,
)

# Allowed forward status transitions. A status may always remain unchanged.
_ALLOWED_TRANSITIONS = {
	"Pending": {"Approved", "Cancelled", "Failed"},
	"Approved": {"Done", "Cancelled", "Failed"},
	"Done": {"Cancelled"},
	"Failed": {"Cancelled"},
	"Cancelled": set(),
}


class FuelRequest(Document):
	def validate(self):
		if (self.requested_litres or 0) <= 0:
			frappe.throw(_("Requested Litres must be greater than zero."))
		self._enforce_status_flow()
		self._stamp_approver()

	def before_submit(self):
		if self._needs_approval():
			ensure_approval("Fuel Request", self.name, required_tier=self._required_tier())

	def on_submit(self):
		if self.status == "Done":
			self._apply_quota_consumption()

	def on_cancel(self):
		self._reverse_quota_consumption()

	# ------------------------------------------------------------------ helpers

	def _enforce_status_flow(self):
		"""Reject illegal status jumps (e.g. Pending->Done, Done->Pending)."""
		new_status = self.status or "Pending"
		previous = self.get_doc_before_save()
		old_status = (previous.status if previous else None) or "Pending"

		if new_status == old_status:
			return

		allowed = _ALLOWED_TRANSITIONS.get(old_status, set())
		if new_status not in allowed:
			frappe.throw(
				_("Cannot change Fuel Request status from {0} to {1}.").format(
					_(old_status), _(new_status)
				)
			)

	def _stamp_approver(self):
		if self.status == "Approved" and not self.approved_by:
			self.approved_by = frappe.session.user

	def _needs_approval(self):
		"""Approval is required when the requested volume exceeds the configured
		threshold, or when this is a cross-project request (its project differs
		from the linked quota's project and cross-project approval is enabled)."""
		settings = get_settings()
		if not getattr(settings, "enable_approvals", 0):
			return False

		threshold = settings.fuel_request_approval_threshold_litres or 0
		if threshold and (self.requested_litres or 0) > threshold:
			return True

		if getattr(settings, "cross_project_needs_approval", 0) and self.project and self.fuel_quota:
			quota_project = frappe.db.get_value("Fuel Quota", self.fuel_quota, "project")
			if quota_project and quota_project != self.project:
				return True

		return False

	def _is_cross_project(self):
		"""True when this request's project differs from the linked quota's project."""
		if not (self.project and self.fuel_quota):
			return False
		quota_project = frappe.db.get_value("Fuel Quota", self.fuel_quota, "project")
		return bool(quota_project and quota_project != self.project)

	def _required_tier(self):
		"""Compute the authority tier this fuel request demands (tiered authorityG08).

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
		log_activity(
			action="Fuel Consumed",
			entity_type="Fuel Quota",
			entity_name=self.fuel_quota,
			details={"fuel_request": self.name, "litres": self.requested_litres},
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
		log_activity(
			action="Fuel Consumption Reversed",
			entity_type="Fuel Quota",
			entity_name=self.fuel_quota,
			details={"fuel_request": self.name, "litres": self.requested_litres},
		)
