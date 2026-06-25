"""Accommodation Assignment controller.

The Assignment record IS the check-in and the active occupancy stay. It carries
both check_in_date and check_out_date; Accommodation Checkout closes it.

Payroll effects are gated behind Habitat Settings and disabled by default.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from apex_habitat.apex_core.utils.party_link import sync_party_employee


class AccommodationAssignment(Document):
    pass


def _flag_temporary_worker_past_expiry(doc) -> None:
    """Soft-flag housing a Temporary Worker whose passport-only window has lapsed.

    Non-blocking on purpose: a supervisor may still need to house an over-window
    worker pending Iqama issuance, so this warns rather than throws. The check-in
    date (or today) is compared against the worker's computed ``expiry_date``.
    """
    if doc.party_type != "Temporary Worker" or not doc.party:
        return
    expiry = frappe.db.get_value("Temporary Worker", doc.party, "expiry_date")
    if not expiry:
        return
    as_of = doc.check_in_date or frappe.utils.today()
    if frappe.utils.getdate(expiry) < frappe.utils.getdate(as_of):
        frappe.msgprint(
            _("Temporary Worker {0}'s stay window expired on {1}.").format(
                doc.party, frappe.utils.formatdate(expiry)
            ),
            indicator="orange",
            alert=True,
        )


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
    sync_party_employee(doc, require_party=True)

    if not doc.building or not frappe.db.exists("Accommodation Building", doc.building):
        return  # [#61pl64]

    building = frappe.get_doc("Accommodation Building", doc.building)

    # [#qwgdi0]
    if not doc.project:
        frappe.throw(_("Project is required."))

    if not doc.cost_center:
        doc.cost_center = building.default_cost_center
    if not doc.cost_center and building.company:
        # [#nid8zr]
        doc.cost_center = frappe.get_cached_value("Company", building.company, "cost_center")
    if not doc.cost_center:
        frappe.throw(
            _("Cost Center is required. Please set it or configure a default Cost Center on Building {0}.").format(
                doc.building
            )
        )

    # [#6nmh1l]
    if doc.stay_type == "Temporary":
        if not doc.expected_checkout_date:
            frappe.throw(_("Expected check-out date is required for temporary stays."))
        if doc.check_in_date and doc.expected_checkout_date < doc.check_in_date:
            frappe.throw(_("Expected check-out date cannot be earlier than the check-in date."))

    # [#ie52i1]
    if doc.employee:
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
    elif doc.party and doc.party_type:
        # [#oa0g50]
        dup = frappe.db.get_value(
            "Accommodation Assignment",
            {
                "party_type": doc.party_type,
                "party": doc.party,
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
                "name": ["!=", doc.name],
            },
            "name",
        )
        if dup:
            frappe.throw(
                _("{0} {1} already has an active Accommodation Assignment: {2}").format(
                    _(doc.party_type), doc.party, dup
                )
            )

    _flag_temporary_worker_past_expiry(doc)

    # [#p7c6qr]
    bed_room = frappe.db.get_value("Accommodation Bed", doc.bed, "room")
    if bed_room != doc.room:
        frappe.throw(_("Selected Bed {0} does not belong to Room {1}").format(doc.bed, doc.room))

    # [#jcdpm8]
    room_doc = frappe.get_doc("Accommodation Room", doc.room)
    if room_doc.building != doc.building:
        frappe.throw(
            _("Selected Room {0} does not belong to Building {1}").format(doc.room, doc.building)
        )
        
    # [#agde2c]
    if room_doc.readiness_status in ["Needs Repair", "Needs Cleaning", "Out of Service"]:
        frappe.throw(
            _("Room {0} is currently '{1}' and cannot be assigned to an employee.").format(
                doc.room, room_doc.readiness_status
            )
        )

    # [#lxozz0]
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
    # [#el1zj2]
    frappe.db.sql(
        "SELECT `status` FROM `tabAccommodation Bed` WHERE `name` = %s FOR UPDATE",
        doc.bed,
    )
    current_status = frappe.db.get_value("Accommodation Bed", doc.bed, "status")
    if current_status == "Occupied":
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
                _("Bed {0} was just taken by another assignment ({1}). Please select a different bed.").format(
                    doc.bed, occupying_asg
                )
            )

    try:
        frappe.db.set_value("Accommodation Bed", doc.bed, "status", "Occupied")
        recalculate_spatial(doc.room, doc.building)
    except Exception:
        frappe.db.rollback()
        frappe.throw(_("Could not update bed occupancy. The assignment was not submitted."))

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
