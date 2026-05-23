"""Accommodation Assignment controller.

The Assignment record IS the check-in and the active occupancy stay. It carries
both check_in_date and check_out_date; Accommodation Checkout closes it.

Payroll effects are gated behind Habitat Settings and disabled by default.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class AccommodationAssignment(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Accommodation Assignment":
            frappe.throw("DocType mismatch")


def recalculate_room_occupancy(room_name: str) -> None:
    if not room_name:
        return
    room = frappe.get_doc("Accommodation Room", room_name)
    if room.status == "Under Maintenance":
        return
    active = frappe.db.count(
        "Accommodation Assignment",
        {"room": room_name, "docstatus": 1, "check_out_date": ["is", "not set"]},
    )
    room.db_set("current_occupancy", active)
    if active <= 0:
        room.db_set("status", "Available")
    elif active >= (room.bed_capacity or 0):
        room.db_set("status", "Full")
    else:
        room.db_set("status", "Partially Occupied")


def recalculate_building_occupancy(building_name: str) -> None:
    if not building_name:
        return
    building = frappe.get_doc("Accommodation Building", building_name)
    active = frappe.db.count(
        "Accommodation Assignment",
        {"building": building_name, "docstatus": 1, "check_out_date": ["is", "not set"]},
    )
    building.db_set("current_occupants", active)
    if building.total_capacity:
        building.db_set("occupancy_percent", (active / building.total_capacity) * 100)


def recalculate_spatial(room_name: str, building_name: str) -> None:
    recalculate_room_occupancy(room_name)
    recalculate_building_occupancy(building_name)


def validate(doc, method=None):
    building = frappe.get_doc("Accommodation Building", doc.building)

    # Project and Cost Center validation
    if not doc.project:
        frappe.throw(_("Project is required."))

    if not doc.cost_center:
        doc.cost_center = building.default_cost_center
    if not doc.cost_center:
        frappe.throw(
            _("Cost Center is required. Please set it or configure a default Cost Center on Building {0}.").format(
                doc.building
            )
        )

    # Reject a second active submitted assignment for the same employee
    active_asg = frappe.db.get_value(
        "Accommodation Assignment",
        {
            "employee": doc.employee,
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
            "name": ["!=", doc.name],
        },
        "name",
    )
    if active_asg:
        frappe.throw(
            _("Employee {0} already has an active Accommodation Assignment: {1}").format(
                doc.employee, active_asg
            )
        )

    # Validate bed belongs to room
    bed_room = frappe.db.get_value("Accommodation Bed", doc.bed, "room")
    if bed_room != doc.room:
        frappe.throw(_("Selected Bed {0} does not belong to Room {1}").format(doc.bed, doc.room))

    # Validate room belongs to building
    room_building = frappe.db.get_value("Accommodation Room", doc.room, "building")
    if room_building != doc.building:
        frappe.throw(
            _("Selected Room {0} does not belong to Building {1}").format(doc.room, doc.building)
        )

    # Validate bed is available
    bed_doc = frappe.get_doc("Accommodation Bed", doc.bed)
    if bed_doc.status == "Out of Service":
        frappe.throw(_("Selected Bed {0} is Out of Service").format(doc.bed))
    elif bed_doc.status == "Occupied":
        occupying_asg = frappe.db.get_value(
            "Accommodation Assignment",
            {
                "bed": doc.bed,
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
                "name": ["!=", doc.name],
            },
            "name",
        )
        if occupying_asg:
            frappe.throw(
                _("Selected Bed {0} is already occupied by Assignment {1}").format(
                    doc.bed, occupying_asg
                )
            )

    active_count = frappe.db.count(
        "Accommodation Assignment",
        {
            "building": doc.building,
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
            "name": ["!=", doc.name],
        },
    )
    capacity = building.total_capacity or 0
    if capacity:
        projected = ((active_count + 1) / capacity) * 100
        if projected > 100 and not building.over_capacity_allowed:
            frappe.throw(
                _("Building is at full capacity ({0} of {1}). Over-capacity not allowed.").format(
                    active_count, capacity
                )
            )
        if projected > (building.over_capacity_threshold_percent or 120):
            frappe.msgprint(
                _("Warning: building occupancy will reach {0:.0f}%.").format(projected),
                indicator="orange",
                alert=True,
            )


def on_submit(doc, method=None):
    frappe.db.set_value("Accommodation Bed", doc.bed, "status", "Occupied")
    recalculate_spatial(doc.room, doc.building)

    settings = frappe.get_single("Habitat Settings")
    activation = settings.deduction_activation_date
    if settings.enable_housing_allowance_deduction and (
        not activation or doc.check_in_date >= activation
    ):
        doc.db_set("housing_allowance_suspended", 1)
        doc.add_comment(
            "Comment",
            "Housing Allowance suspended per Habitat Settings.",
        )
    else:
        doc.db_set("housing_allowance_suspended", 0)
        doc.add_comment(
            "Comment",
            "Housing Allowance not suspended - feature disabled in Habitat Settings.",
        )


def on_cancel(doc, method=None):
    active_on_bed = frappe.db.count(
        "Accommodation Assignment",
        {
            "bed": doc.bed,
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
            "name": ["!=", doc.name],
        },
    )
    if active_on_bed == 0:
        frappe.db.set_value("Accommodation Bed", doc.bed, "status", "Available")

    recalculate_spatial(doc.room, doc.building)
