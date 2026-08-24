# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from apex.salis.utils import add_timeline_note, lock_driver, lock_vehicle, set_current_driver
from apex.salis.utils.driver_availability import planned_trips_for_driver

_CLOSED_FUEL_EXCEPTION_STATUSES = ("Resolved", "Rejected", "Closed")

_CLOSED_RECOVERY_STATUSES = ("Recovered", "Waived", "Rejected", "Cancelled")

VALID_STATUSES = ("Open", "In Progress", "Cleared", "Blocked", "Cancelled")


class DriverClearance(Document):
    def validate(self):
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))
        self._compute_outstanding()
        self._guard_cleared_status()
        self._stamp_clearance_date()

    def on_submit(self):
        if self.status == "Cleared":
            self._release_driver()

    def on_cancel(self):
        if self.status == "Cleared":
            self._restore_driver()

    def _compute_outstanding(self):
        self.outstanding_fuel_exceptions = self._count_open(
            "Fuel Exception Case", _CLOSED_FUEL_EXCEPTION_STATUSES
        )
        self.outstanding_recoveries = self._count_open(
            "Movement Cost Recovery", _CLOSED_RECOVERY_STATUSES
        )
        self.outstanding_recovery_amount = self._sum_open_recoveries()

    def _sum_open_recoveries(self):
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
        if self.status == "Cleared":
            if not self.clearance_date:
                self.clearance_date = nowdate()
            return
        self.clearance_date = None

    def _count_open(self, doctype, closed_statuses):
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
        planned = planned_trips_for_driver(self.driver)
        if planned:
            missing.append(
                _("Planned trips still assigned to him ({0})").format(", ".join(planned[:5]))
            )

        if missing:
            frappe.throw(
                _("Clearance is blocked. The following must be resolved first: {0}.").format(
                    ", ".join(missing)
                )
            )

    def _release_driver(self):
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
                set_current_driver(current_vehicle, None)
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
