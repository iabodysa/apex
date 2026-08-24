# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.salis.utils import (
    add_timeline_note,
    validate_vehicle_compliance,
    lock_vehicle,
    lock_driver,
    rider_block_reason,
    set_current_driver,
    vehicle_is_held_out_of_service,
)


class VehicleAssignment(Document):
    def validate(self):
        self._validate_dates()
        self._validate_no_overlap()
        validate_vehicle_compliance(self)
        self._enforce_rider_active()

    def _enforce_rider_active(self):
        if not self.driver:
            return
        reason = rider_block_reason(self.driver, self.start_date)
        if reason:
            frappe.throw(reason)

    def _validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            frappe.throw(_("End Date cannot be earlier than Start Date."))

    def _overlapping(self, field, value):
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

        if vehicle_is_held_out_of_service(self.vehicle):
            set_current_driver(self.vehicle, self.driver)
        else:
            set_current_driver(self.vehicle, self.driver, status="Active")
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
        if frappe.db.get_value("Salis Vehicle", self.vehicle, "current_driver") == self.driver:
            set_current_driver(self.vehicle, None)
        if frappe.db.get_value("Salis Driver", self.driver, "current_vehicle") == self.vehicle:
            frappe.db.set_value("Salis Driver", self.driver, "current_vehicle", None)

        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Assignment {0} (driver {1}) cancelled.").format(self.name, self.driver),
        )
