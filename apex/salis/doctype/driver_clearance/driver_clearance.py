# Copyright (c) 2026, afmcoltd
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
from frappe.utils import flt, nowdate

from apex.salis.utils import add_timeline_note, lock_driver, lock_vehicle

_CLOSED_FUEL_EXCEPTION_STATUSES = ("Resolved", "Rejected", "Closed")

_CLOSED_RECOVERY_STATUSES = ("Recovered", "Waived", "Rejected", "Cancelled")

VALID_STATUSES = ("Open", "In Progress", "Cleared", "Blocked", "Cancelled")


class DriverClearance(Document):
    def validate(self):
        """Recomputes the driver's open fuel-exception and recovery counts and blocks marking Cleared."""
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))
        self._capture_assigned_vehicle()
        self._compute_outstanding()
        self._guard_cleared_status()
        self._stamp_clearance_date()

    def on_submit(self):
        """Releases the driver to Released status and clears their vehicle when submitted as Cleared."""
        if self.status == "Cleared":
            self._release_driver()

    def on_cancel(self):
        """Restores a Released driver back to Active when a Cleared clearance is cancelled."""
        if self.status == "Cleared":
            self._restore_driver()


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
        self.outstanding_recovery_amount = self._sum_open_recoveries()

    def _sum_open_recoveries(self):
        """The money still open against the driver, not the number of cases.

        HR withholds a sum from a final settlement, and a count of three open cases does
        not say whether to hold ten riyals or ten thousand. Returns zero when the driver
        is unset or the recovery DocType is not on the site, so the certificate reads
        nothing owed rather than refusing to print.
        """
        if not self.driver or not frappe.db.exists("DocType", "Movement Cost Recovery"):
            return 0
        rows = frappe.get_all(
            "Movement Cost Recovery",
            filters={
                "driver": self.driver,
                "docstatus": ["!=", 2],
                "status": ["not in", list(_CLOSED_RECOVERY_STATUSES)],
            },
            fields=["amount"],
        )
        return sum(flt(row.amount) for row in rows)

    def _stamp_clearance_date(self):
        """Record the day the clearance was granted, and clear it if the clearance is withdrawn.

        A certificate that releases a final settlement must say when it was granted; HR
        pays against a date, not against a status. The stamp goes on the moment the
        clearance reads Cleared and comes off the moment it does not, so a blocked or
        reopened clearance never prints a release date it no longer has.
        """
        if self.status == "Cleared":
            if not self.clearance_date:
                self.clearance_date = nowdate()
            return
        self.clearance_date = None

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
                "docstatus": ["!=", 2],
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
        """Move the driver to Released and clear both sides of the current vehicle link.

		Guarded: only releases an existing driver, and only clears a vehicle
		reference when one is set. Row-locks the driver to avoid races with
		concurrent assignment/handover."""
        if not self.driver or not frappe.db.exists("Salis Driver", self.driver):
            return

        lock_driver(self.driver)
        updates = {"status": "Released"}
        current_vehicle = frappe.db.get_value("Salis Driver", self.driver, "current_vehicle")
        if current_vehicle:
            lock_vehicle(current_vehicle)
            if (
                frappe.db.get_value("Salis Vehicle", current_vehicle, "current_driver")
                == self.driver
            ):
                frappe.db.set_value("Salis Vehicle", current_vehicle, "current_driver", None)
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

    def _restore_driver(self):
        """Reverse _release_driver on cancel: move a still-Released driver back to
		Active. Row-locked; a no-op if the driver no longer exists or has already
		moved off Released (e.g. a later assignment), so a fresh assignment is never
		clobbered."""
        if not self.driver or not frappe.db.exists("Salis Driver", self.driver):
            return
        lock_driver(self.driver)
        if frappe.db.get_value("Salis Driver", self.driver, "status") != "Released":
            return
        frappe.db.set_value("Salis Driver", self.driver, "status", "Active")
        add_timeline_note(
            "Salis Driver",
            self.driver,
            _("Clearance {0} cancelled; driver restored to Active.").format(self.name),
        )
