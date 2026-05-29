"""Driver Clearance controller.

Movement-domain exit clearance for a driver. Confirms the driver has returned
the vehicle, fuel chip, and custody items, and blocks clearance while any open
Fuel Exception Case or Movement Cost Recovery remains against the driver. HR
end-of-service and visa clearance are handled outside this module.

Status transitions are owned by the native **Driver Clearance Workflow** (see
``salis/workflow/driver_clearance_workflow/``), not by this controller. The
"Clear" transition (which submits the document) is gated by a workflow
``condition`` mirroring the precondition guard below — it is only offered once
the vehicle, fuel chip and custody are returned and no open Fuel Exception Case
or Movement Cost Recovery remains. ``_guard_cleared_status`` stays as the hard
server-side block (defence in depth: it fires on any save that lands the
document in Cleared, including a path that bypasses the workflow action).

On submit of a Cleared clearance the linked Salis Driver is moved to Released
and its current vehicle reference is cleared (guarded), so the released driver
no longer holds an assignment.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import add_timeline_note, lock_driver

# Statuses that mean a Fuel Exception Case is no longer outstanding.
_CLOSED_FUEL_EXCEPTION_STATUSES = ("Resolved", "Rejected", "Closed")

# Statuses that mean a Movement Cost Recovery is no longer outstanding. Kept
# broad because the doctype is being introduced in parallel; the query is
# guarded by an existence check so a missing doctype never breaks clearance.
_CLOSED_RECOVERY_STATUSES = ("Recovered", "Closed", "Cancelled", "Written Off", "Resolved")

# Known status values. The Select carries these for filtering/colour, but the
# Driver Clearance Workflow owns the *transitions*.
VALID_STATUSES = ("Open", "In Progress", "Cleared", "Blocked", "Cancelled")


class DriverClearance(Document):
	def validate(self):
		if self.status and self.status not in VALID_STATUSES:
			frappe.throw(_("Invalid status: {0}").format(self.status))
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

		add_timeline_note(
			"Salis Driver",
			self.driver,
			_("Cleared and released via {0} (reason {1}; vehicle {2}).").format(
				self.name,
				_(self.clearance_reason) if self.clearance_reason else _("n/a"),
				current_vehicle or _("none"),
			),
		)
