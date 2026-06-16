"""Vehicle Incident controller.

Records a fleet incident event - an accident or a theft - against a vehicle.
This is the event of record (location, report number, fault, evidence); it is
distinct from a Vehicle Damage Write-Off (the disposition/authority gate) and a
Vehicle Stop (the state change). A submitted Theft incident takes the vehicle out
of service and clears its driver, capturing the prior state so a cancel reverses
it cleanly. An Accident incident records the event only; stopping the vehicle, if
needed, is a separate Vehicle Stop.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

from apex_habitat.salis.utils import add_timeline_note, lock_vehicle


class VehicleIncident(Document):
    def validate(self):
        # [#90trn2]
        if self.incident_date and getdate(self.incident_date) > getdate(today()):
            frappe.throw(_("Incident date cannot be in the future."))

    def on_submit(self):
        # [#e0k92e]
        if self.incident_type != "Theft":
            return

        lock_vehicle(self.vehicle)

        # [#3i7mrn]
        prev_status, prev_driver = frappe.db.get_value(
            "Salis Vehicle", self.vehicle, ["status", "current_driver"]
        )
        self.db_set("previous_vehicle_status", prev_status)
        self.db_set("previous_driver", prev_driver)

        # [#qwhpba]
        frappe.db.set_value(
            "Salis Vehicle",
            self.vehicle,
            {"status": "Stopped", "current_driver": None},
        )
        if prev_driver:
            frappe.db.set_value("Salis Driver", prev_driver, "current_vehicle", None)

        self.add_comment("Comment", _("Vehicle {0} reported stolen.").format(self.vehicle))
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Reported stolen via {0}.").format(self.name),
        )

    def on_cancel(self):
        if self.incident_type != "Theft":
            return

        lock_vehicle(self.vehicle)

        # [#nes9rz]
        # [#mp48se]
        if self.previous_driver and not frappe.db.get_value(
            "Salis Vehicle", self.vehicle, "current_driver"
        ):
            frappe.db.set_value(
                "Salis Vehicle", self.vehicle, "current_driver", self.previous_driver
            )
            frappe.db.set_value(
                "Salis Driver", self.previous_driver, "current_vehicle", self.vehicle
            )

        # [#aj24lr]
        # [#82mq04]
        another_stop_in_force = frappe.db.exists(
            "Vehicle Stop", {"vehicle": self.vehicle, "docstatus": 1}
        )
        if (
            not another_stop_in_force
            and frappe.db.get_value("Salis Vehicle", self.vehicle, "status") == "Stopped"
        ):
            frappe.db.set_value(
                "Salis Vehicle",
                self.vehicle,
                "status",
                self.previous_vehicle_status or "Active",
            )

        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Theft report {0} cancelled.").format(self.name),
        )
