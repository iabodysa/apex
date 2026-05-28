"""Driver Clearance controller.

Movement-domain exit clearance for a driver. Confirms the driver has returned
the vehicle, fuel chip, and custody items, and blocks clearance while any open
Fuel Exception Case or Movement Cost Recovery remains against the driver. HR
end-of-service and visa clearance are handled outside this module.

On submit of a Cleared clearance the linked Salis Driver is moved to Released
and its current vehicle reference is cleared (guarded), so the released driver
no longer holds an assignment.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import lock_driver, log_activity

# Statuses that mean a Fuel Exception Case is no longer outstanding.
_CLOSED_FUEL_EXCEPTION_STATUSES = ("Resolved", "Rejected", "Closed")

# Statuses that mean a Movement Cost Recovery is no longer outstanding. Kept
# broad because the doctype is being introduced in parallel; the query is
# guarded by an existence check so a missing doctype never breaks clearance.
_CLOSED_RECOVERY_STATUSES = ("Recovered", "Closed", "Cancelled", "Written Off", "Resolved")


class DriverClearance(Document):
	def validate(self):
		self._capture_assigned_vehicle()
		self._compute_outstanding()
		self._guard_cleared_status()

	def on_submit(self):
		if self.status == "Cleared":
			self._release_driver()

	# ------------------------------------------------------------------ helpers

	def _capture_assigned_vehicle(self):
		"""Snapshot the driver's current vehicle for reference (read-only field)."""
		if self.driver and not self.assigned_vehicle:
			self.assigned_vehicle = frappe.db.get_value(
				"Salis Driver", self.driver, "current_vehicle"
			)

	def _compute_outstanding(self):
		"""Recompute the outstanding open-case counters for the driver."""
		self.outstanding_fuel_exceptions = self._count_open(
			"Fuel Exception Case", _CLOSED_FUEL_EXCEPTION_STATUSES
		)
		self.outstanding_recoveries = self._count_open(
			"Movement Cost Recovery", _CLOSED_RECOVERY_STATUSES
		)

	def _count_open(self, doctype, closed_statuses):
		"""Count records of ``doctype`` for this driver whose status is not in
		``closed_statuses``. Returns 0 when the driver is unset or the doctype
		does not yet exist (it may be delivered in a parallel slice)."""
		if not self.driver:
			return 0
		if not frappe.db.exists("DocType", doctype):
			return 0
		return frappe.db.count(
			doctype,
			filters={
				"driver": self.driver,
				"status": ["not in", list(closed_statuses)],
			},
		)

	def _guard_cleared_status(self):
		"""Refuse to mark a clearance Cleared while any precondition is unmet."""
		if self.status != "Cleared":
			return

		missing = []
		if not self.vehicle_returned:
			missing.append(_("Vehicle Returned"))
		if not self.fuel_chip_returned:
			missing.append(_("Fuel Chip Returned"))
		if not self.custody_returned:
			missing.append(_("Custody Returned"))
		if (self.outstanding_fuel_exceptions or 0) != 0:
			missing.append(_("Open Fuel Exception Cases"))
		if (self.outstanding_recoveries or 0) != 0:
			missing.append(_("Open Movement Cost Recoveries"))

		if missing:
			frappe.throw(
				_("Clearance is blocked. The following must be resolved first: {0}.").format(
					", ".join(missing)
				)
			)

	def _release_driver(self):
		"""Move the driver to Released and clear the current vehicle link.

		Guarded: only releases an existing driver, and only clears a vehicle
		reference when one is set. Row-locks the driver to avoid races with
		concurrent assignment/handover."""
		if not self.driver or not frappe.db.exists("Salis Driver", self.driver):
			return

		lock_driver(self.driver)
		updates = {"status": "Released"}
		current_vehicle = frappe.db.get_value("Salis Driver", self.driver, "current_vehicle")
		if current_vehicle:
			updates["current_vehicle"] = None
		frappe.db.set_value("Salis Driver", self.driver, updates)

		log_activity(
			action="Driver Cleared",
			entity_type="Salis Driver",
			entity_name=self.driver,
			details={
				"driver_clearance": self.name,
				"clearance_reason": self.clearance_reason,
				"released_vehicle": current_vehicle,
			},
		)
