"""Vehicle Stop controller.

Stops a vehicle, capturing its prior status into previous_status so the effect
can be reliably reversed on cancel.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import lock_vehicle, log_activity


class VehicleStop(Document):
    def validate(self):
        if self.vehicle and not self.ownership_at_stop:
            self.ownership_at_stop = frappe.db.get_value("Salis Vehicle", self.vehicle, "ownership")

    def on_submit(self):
        lock_vehicle(self.vehicle)

        # Capture the prior status for a reliable revert on cancel.
        self.db_set("previous_status", frappe.db.get_value("Salis Vehicle", self.vehicle, "status"))

        frappe.db.set_value("Salis Vehicle", self.vehicle, "status", "Stopped")

        self.add_comment("Comment", _("Vehicle {0} stopped: {1}.").format(self.vehicle, self.stop_reason))
        log_activity(
            action="Vehicle Stopped",
            entity_type="Salis Vehicle",
            entity_name=self.vehicle,
            details={"stop": self.name, "reason": self.stop_reason},
        )

    def on_cancel(self):
        lock_vehicle(self.vehicle)

        # Restore only if the vehicle is still in the state this stop set
        # (a later stop may have changed it).
        if frappe.db.get_value("Salis Vehicle", self.vehicle, "status") == "Stopped":
            restore = self.previous_status or "Active"
            frappe.db.set_value("Salis Vehicle", self.vehicle, "status", restore)

        log_activity(
            action="Vehicle Stop Cancelled",
            entity_type="Salis Vehicle",
            entity_name=self.vehicle,
            details={"stop": self.name},
        )
