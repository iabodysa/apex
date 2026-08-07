# Copyright (c) 2026, afmcoltd
"""Vehicle Assignment controller.

The submitted Vehicle Assignment is the authoritative vehicle<->driver pairing.
Salis Vehicle.current_driver and Salis Driver.current_vehicle are denormalized
mirrors written from here via set_value.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.salis.utils import (
    add_timeline_note,
    enforce_vehicle_compliance,
    lock_vehicle,
    lock_driver,
    rider_block_reason,
)


class VehicleAssignment(Document):
    def validate(self):
        """Validates dates, blocks an overlapping assignment, checks compliance and rider status."""
        self._validate_dates()
        self._validate_no_overlap()
        enforce_vehicle_compliance(self)
        self._enforce_rider_active()

    def _enforce_rider_active(self):
        """Block assigning a vehicle to a rider who is on leave / inactive.

        Source of truth is the rider's HRMS Employee status and any approved
        Leave Application covering the assignment start date (falls back to the
        local Salis Driver status). A new assignment puts a company vehicle in
        the rider's custody, so an offboarded / on-leave rider must be rejected.
        """
        if not self.driver:
            return
        reason = rider_block_reason(self.driver, self.start_date)
        if reason:
            frappe.throw(reason)

    def _validate_dates(self):
        """Requires the end date to be no earlier than the start date."""
        if self.start_date and self.end_date and self.end_date < self.start_date:
            frappe.throw(_("End Date cannot be earlier than Start Date."))

    def _overlapping(self, field, value):
        """Return the name of a submitted, Active assignment for the same
        vehicle/driver whose period overlaps this document's period.

        Open-ended periods (no end_date) run to infinity. Two ranges
        [a_start, a_end] and [b_start, b_end] overlap when
        a_start <= b_end AND b_start <= a_end.
        """
        if not value:
            return None
        candidates = frappe.get_all(
            "Vehicle Assignment",
            filters={
                field: value,
                "docstatus": 1,
                "status": "Active",
                "name": ["!=", self.name],
            },
            fields=["name", "start_date", "end_date"],
        )
        self_start = str(self.start_date or "1900-01-01")
        self_end = str(self.end_date or "9999-12-31")
        for c in candidates:
            other_start = str(c.start_date or "1900-01-01")
            other_end = str(c.end_date or "9999-12-31")
            if self_start <= other_end and other_start <= self_end:
                return c.name
        return None

    def _validate_no_overlap(self):
        """Blocks the assignment when its vehicle or driver already has an overlapping active one."""
        clash = self._overlapping("vehicle", self.vehicle)
        if clash:
            frappe.throw(
                _("Vehicle {0} already has an active assignment {1}.").format(self.vehicle, clash)
            )
        clash = self._overlapping("driver", self.driver)
        if clash:
            frappe.throw(
                _("Driver {0} already has an active assignment {1}.").format(self.driver, clash)
            )

    def on_submit(self):
        """Links the vehicle and driver as each other's current pairing and rechecks for a race overlap."""
        lock_vehicle(self.vehicle)
        lock_driver(self.driver)

        clash = self._overlapping("vehicle", self.vehicle)
        if clash:
            frappe.throw(
                _("Vehicle {0} was just assigned by {1}. Please review.").format(self.vehicle, clash)
            )
        clash = self._overlapping("driver", self.driver)
        if clash:
            frappe.throw(
                _("Driver {0} was just assigned by {1}. Please review.").format(self.driver, clash)
            )

        frappe.db.set_value(
            "Salis Vehicle",
            self.vehicle,
            {"current_driver": self.driver, "status": "Active"},
        )
        frappe.db.set_value("Salis Driver", self.driver, "current_vehicle", self.vehicle)

        self.add_comment(
            "Comment", _("Vehicle {0} assigned to driver {1}.").format(self.vehicle, self.driver)
        )
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Assigned to driver {0} via {1}.").format(self.driver, self.name),
        )

    def on_cancel(self):
        """Clears the vehicle-driver pairing this assignment set, if it is still in place."""
        if frappe.db.get_value("Salis Vehicle", self.vehicle, "current_driver") == self.driver:
            frappe.db.set_value("Salis Vehicle", self.vehicle, "current_driver", None)
        if frappe.db.get_value("Salis Driver", self.driver, "current_vehicle") == self.vehicle:
            frappe.db.set_value("Salis Driver", self.driver, "current_vehicle", None)

        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Assignment {0} (driver {1}) cancelled.").format(self.name, self.driver),
        )
