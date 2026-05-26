"""Fuel Topup Request controller.

Submittable fuel top-up request. Temporary top-ups must carry a revert due date
and are auto-reverted by the daily Salis scheduler once overdue; this controller
only surfaces a warning for the overdue case and guards status transitions.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from apex_habitat.salis.salis_lib import ensure_approval, get_settings, log_activity

# Allowed forward status transitions. A status may always remain unchanged.
_ALLOWED_TRANSITIONS = {
	"Pending": {"Approved", "Cancelled"},
	"Approved": {"Done", "Cancelled"},
	"Done": {"Reverted", "Cancelled"},
	"Reverted": {"Cancelled"},
	"Cancelled": set(),
}


class FuelTopupRequest(Document):
	def validate(self):
		if (self.topup_litres or 0) <= 0:
			frappe.throw(_("Top-up Litres must be greater than zero."))
		if self.is_temporary and not self.revert_due_date:
			frappe.throw(_("A temporary top-up requires a revert due date."))
		self._enforce_status_flow()
		self._warn_overdue_temporary()

	def before_submit(self):
		if self._needs_approval():
			ensure_approval("Fuel Topup Request", self.name)

	def on_submit(self):
		log_activity(
			action="Fuel Topup",
			entity_type="Salis Vehicle",
			entity_name=self.vehicle,
			details={
				"fuel_topup_request": self.name,
				"litres": self.topup_litres,
				"is_temporary": bool(self.is_temporary),
			},
		)

	def on_cancel(self):
		log_activity(
			action="Fuel Topup Cancelled",
			entity_type="Salis Vehicle",
			entity_name=self.vehicle,
			details={"fuel_topup_request": self.name, "litres": self.topup_litres},
		)

	# ------------------------------------------------------------------ helpers

	def _enforce_status_flow(self):
		new_status = self.status or "Pending"
		previous = self.get_doc_before_save()
		old_status = (previous.status if previous else None) or "Pending"

		if new_status == old_status:
			return

		allowed = _ALLOWED_TRANSITIONS.get(old_status, set())
		if new_status not in allowed:
			frappe.throw(
				_("Cannot change Fuel Topup Request status from {0} to {1}.").format(
					_(old_status), _(new_status)
				)
			)

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

	def _needs_approval(self):
		"""Approval is required above the configured litre threshold, or for a
		cross-project top-up when cross-project approval is enabled."""
		settings = get_settings()
		if not getattr(settings, "enable_approvals", 0):
			return False

		threshold = settings.fuel_request_approval_threshold_litres or 0
		if threshold and (self.topup_litres or 0) > threshold:
			return True

		if getattr(settings, "cross_project_needs_approval", 0) and self.project and self.vehicle:
			vehicle_project = frappe.db.get_value("Salis Vehicle", self.vehicle, "project")
			if vehicle_project and vehicle_project != self.project:
				return True

		return False
