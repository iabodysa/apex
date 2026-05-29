"""Vehicle Assignment controller.

The submitted Vehicle Assignment is the authoritative vehicle<->driver pairing.
Salis Vehicle.current_driver and Salis Driver.current_vehicle are denormalized
mirrors written from here via set_value.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import add_timeline_note, lock_vehicle, lock_driver


class VehicleAssignment(Document):
    def validate(self):
        self._validate_dates()
        self._validate_no_overlap()
        self._enforce_compliance()

    def _enforce_compliance(self):
        """Block (or warn) when the linked vehicle's compliance has expired.

        Reads Salis Vehicle.compliance_status; if Expired, honours the
        Salis Settings.block_assignment_on_expired_compliance flag: block when
        set, otherwise warn. Safe default = warn.
        """
        if not self.vehicle:
            return
        status = frappe.db.get_value("Salis Vehicle", self.vehicle, "compliance_status")
        if status != "Expired":
            return
        if frappe.db.get_single_value(
            "Salis Settings", "block_assignment_on_expired_compliance"
        ):
            frappe.throw(
                _("Vehicle {0} has expired compliance and cannot be dispatched/assigned.").format(
                    self.vehicle
                )
            )
        else:
            frappe.msgprint(
                _("Warning: vehicle {0} has expired compliance.").format(self.vehicle),
                indicator="orange",
            )

    def _validate_dates(self):
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
        lock_vehicle(self.vehicle)
        lock_driver(self.driver)

        # Re-check inside the lock to guard against a concurrent submission.
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
        # Only clear the mirrors if they still point at THIS pairing; a newer
        # assignment may have already overwritten them.
        if frappe.db.get_value("Salis Vehicle", self.vehicle, "current_driver") == self.driver:
            frappe.db.set_value("Salis Vehicle", self.vehicle, "current_driver", None)
        if frappe.db.get_value("Salis Driver", self.driver, "current_vehicle") == self.vehicle:
            frappe.db.set_value("Salis Driver", self.driver, "current_vehicle", None)

        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Assignment {0} (driver {1}) cancelled.").format(self.name, self.driver),
        )
