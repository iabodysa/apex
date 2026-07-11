# Copyright (c) 2026, AFMCO and contributors
"""Vehicle Incident controller.

Records a fleet incident event - an accident or a theft - against a vehicle.
This is the event of record (location, report number, fault, evidence); it is
distinct from a Vehicle Damage Write-Off (the disposition/authority gate) and a
Vehicle Suspension (the state change). A submitted Theft incident takes the vehicle out
of service and clears its driver, capturing the prior state so a cancel reverses
it cleanly. An Accident incident records the event only; stopping the vehicle, if
needed, is a separate Vehicle Suspension.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

from apex.salis.utils import add_timeline_note, lock_vehicle


class VehicleIncident(Document):
    def validate(self):
        # [#cuwq5w]
        if self.incident_date and getdate(self.incident_date) > getdate(today()):
            frappe.throw(_("Incident date cannot be in the future."))
        # [#82nrhv]
        if flt(self.estimated_cost) < 0:
            frappe.throw(_("Estimated cost cannot be negative."))
        self._guard_public_intake()

    def _guard_public_intake(self):
        # [#pt70xv]
        if self.is_new() and frappe.session.user == "Guest":
            # [#mwj4rl]
            self.status = "Open"
            for field in ("write_off_case", "previous_status", "previous_driver"):
                self.set(field, None)

        # [#gytrj6]
        for field, limit in (("description", 4000), ("location", 280), ("report_number", 140), ("reported_by", 140)):
            value = self.get(field)
            if value and len(value) > limit:
                frappe.throw(_("{0} is too long.").format(_(self.meta.get_label(field))))

    def on_submit(self):
        # [#2gzgc9]
        if self.incident_type != "Theft":
            return

        lock_vehicle(self.vehicle)

        # [#d721f6]
        prev_status, prev_driver = frappe.db.get_value(
            "Salis Vehicle", self.vehicle, ["status", "current_driver"]
        )
        self.db_set("previous_status", prev_status)
        self.db_set("previous_driver", prev_driver)

        # [#558p5y]
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

        # [#pq10av]
        if self.previous_driver and not frappe.db.get_value(
            "Salis Vehicle", self.vehicle, "current_driver"
        ):
            frappe.db.set_value(
                "Salis Vehicle", self.vehicle, "current_driver", self.previous_driver
            )
            frappe.db.set_value(
                "Salis Driver", self.previous_driver, "current_vehicle", self.vehicle
            )

        # [#nbueah]
        another_stop_in_force = frappe.db.exists(
            "Vehicle Suspension", {"vehicle": self.vehicle, "docstatus": 1}
        )
        if (
            not another_stop_in_force
            and frappe.db.get_value("Salis Vehicle", self.vehicle, "status") == "Stopped"
        ):
            frappe.db.set_value(
                "Salis Vehicle",
                self.vehicle,
                "status",
                self.previous_status or "Active",
            )

        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Theft report {0} cancelled.").format(self.name),
        )
