"""Room Bed Transfer controller.

In-place move of an active occupant from one bed to another without closing
and re-opening the Accommodation Assignment.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class RoomBedTransfer(Document):
    def validate(self):
        if not self.to_bed or not self.to_room:
            return  # Mandatory check will catch missing fields

        bed_status = frappe.db.get_value("Accommodation Bed", self.to_bed, "status")
        if bed_status == "Out of Service":
            frappe.throw(_("Target Bed {0} is Out of Service.").format(self.to_bed))
        elif bed_status == "Occupied":
            frappe.throw(_("Target bed is already occupied."))

        # Validate target bed belongs to target room
        bed_room = frappe.db.get_value("Accommodation Bed", self.to_bed, "room")
        if bed_room is not None and bed_room != self.to_room:
            frappe.throw(_("Target Bed {0} does not belong to Room {1}").format(self.to_bed, self.to_room))

        # Validate target room belongs to building
        to_building = frappe.db.get_value("Accommodation Room", self.to_room, "building")
        if to_building is not None and not to_building:
            frappe.throw(_("Target Room {0} is not associated with any Building.").format(self.to_room))

    def on_submit(self):
        frappe.db.set_value("Accommodation Bed", self.from_bed, "status", "Available")
        frappe.db.set_value("Accommodation Bed", self.to_bed, "status", "Occupied")
        to_building = frappe.db.get_value("Accommodation Room", self.to_room, "building")
        assignment = frappe.get_doc("Accommodation Assignment", self.assignment)
        assignment.db_set("bed", self.to_bed)
        assignment.db_set("room", self.to_room)
        assignment.db_set("building", to_building)

    def on_cancel(self):
        frappe.db.set_value("Accommodation Bed", self.to_bed, "status", "Available")
        frappe.db.set_value("Accommodation Bed", self.from_bed, "status", "Occupied")
