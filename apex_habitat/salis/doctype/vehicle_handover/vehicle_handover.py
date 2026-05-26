"""Vehicle Handover controller.

Transfers a vehicle from one driver to another, updating the vehicle's
current_driver mirror and odometer. The submitted Vehicle Assignment remains
the authoritative pairing; this controller only updates the denormalized mirror.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import lock_vehicle, log_activity


class VehicleHandover(Document):
    def validate(self):
        if self.from_driver and self.to_driver and self.from_driver == self.to_driver:
            frappe.throw(_("To Driver must differ from From Driver."))

        if self.vehicle and self.odometer_reading is not None:
            current = frappe.db.get_value("Salis Vehicle", self.vehicle, "odometer") or 0
            if self.odometer_reading < current:
                frappe.throw(
                    _("Odometer reading {0} cannot be lower than the vehicle's current {1}.").format(
                        self.odometer_reading, current
                    )
                )

    def on_submit(self):
        lock_vehicle(self.vehicle)

        frappe.db.set_value(
            "Salis Vehicle",
            self.vehicle,
            {"current_driver": self.to_driver, "odometer": self.odometer_reading},
        )

        # Detach the old driver if its mirror still points at this vehicle.
        if self.from_driver and (
            frappe.db.get_value("Salis Driver", self.from_driver, "current_vehicle") == self.vehicle
        ):
            frappe.db.set_value("Salis Driver", self.from_driver, "current_vehicle", None)

        if self.to_driver:
            frappe.db.set_value("Salis Driver", self.to_driver, "current_vehicle", self.vehicle)

        self.add_comment(
            "Comment",
            _("Vehicle {0} handed over to driver {1}.").format(self.vehicle, self.to_driver),
        )
        log_activity(
            action="Vehicle Handover",
            entity_type="Salis Vehicle",
            entity_name=self.vehicle,
            details={
                "handover": self.name,
                "from_driver": self.from_driver,
                "to_driver": self.to_driver,
                "odometer": self.odometer_reading,
            },
        )

    def on_cancel(self):
        lock_vehicle(self.vehicle)

        # Revert current_driver only if it still points at the to_driver this
        # handover set (a later handover may have moved it again).
        if frappe.db.get_value("Salis Vehicle", self.vehicle, "current_driver") == self.to_driver:
            frappe.db.set_value("Salis Vehicle", self.vehicle, "current_driver", self.from_driver)

            # Restore the driver<->vehicle mirror to the from_driver.
            if self.to_driver and (
                frappe.db.get_value("Salis Driver", self.to_driver, "current_vehicle") == self.vehicle
            ):
                frappe.db.set_value("Salis Driver", self.to_driver, "current_vehicle", None)
            if self.from_driver:
                frappe.db.set_value("Salis Driver", self.from_driver, "current_vehicle", self.vehicle)

        log_activity(
            action="Vehicle Handover Cancelled",
            entity_type="Salis Vehicle",
            entity_name=self.vehicle,
            details={"handover": self.name},
        )
