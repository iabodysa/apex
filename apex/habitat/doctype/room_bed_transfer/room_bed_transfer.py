# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.party_link import sync_party_employee
from apex.habitat.doctype.housing_assignment.housing_assignment import recalculate_spatial


class RoomBedTransfer(Document):

    def before_submit(self):
        before_submit(self)

    def before_cancel(self):
        before_cancel(self)


def _source_building(doc):
    building = None
    if doc.assignment:
        building = frappe.db.get_value("Housing Assignment", doc.assignment, "building")
    if not building and doc.from_bed:
        building = frappe.db.get_value("Bed", doc.from_bed, "building")
    return building


def validate(doc, method=None):
    sync_party_employee(doc, derive_from="assignment")

    if not doc.to_bed or not doc.to_room:
        return

    bed_status = frappe.db.get_value("Bed", doc.to_bed, "status")
    if bed_status == "Out of Service":
        frappe.throw(_("Target Bed {0} is Out of Service.").format(doc.to_bed))
    elif bed_status == "Occupied":
        frappe.throw(_("Target bed is already occupied."))

    bed_room = frappe.db.get_value("Bed", doc.to_bed, "room")
    if bed_room is not None and bed_room != doc.to_room:
        frappe.throw(_("Target Bed {0} does not belong to Room {1}").format(doc.to_bed, doc.to_room))

    to_building = frappe.db.get_value("Room", doc.to_room, "building")
    if not to_building:
        frappe.throw(_("Target Room {0} is not associated with any Building.").format(doc.to_room))

    from_building = _source_building(doc)
    if from_building and from_building != to_building:
        frappe.throw(
            _("Cross-building moves are not supported here. Use Check-out and a new Check-in.")
        )


def before_submit(doc, method=None):
    asg = frappe.db.get_value(
        "Housing Assignment",
        doc.assignment,
        ["docstatus", "check_out_date", "bed"],
        as_dict=True,
        for_update=True,
    )
    if not asg or asg.docstatus != 1 or asg.check_out_date:
        frappe.throw(_("This transfer needs an active (checked-in) assignment to move."))

    if asg.bed != doc.from_bed:
        frappe.throw(
            _("This transfer was raised from Bed {0} but the resident is now in Bed {1}.").format(
                doc.from_bed, asg.bed
            )
        )


def on_submit(doc, method=None):
    asg = frappe.db.get_value(
        "Housing Assignment", doc.assignment, ["room", "building"], as_dict=True
    )

    locked_status = frappe.db.get_value("Bed", doc.to_bed, "status", for_update=True)
    if locked_status == "Out of Service":
        frappe.throw(_("Target Bed {0} is Out of Service.").format(doc.to_bed))
    if locked_status == "Occupied":
        frappe.throw(_("Target bed is already occupied."))

    frappe.db.set_value("Bed", doc.from_bed, "status", "Available")
    frappe.db.set_value("Bed", doc.to_bed, "status", "Occupied")
    to_building = frappe.db.get_value("Room", doc.to_room, "building")
    assignment = frappe.get_doc("Housing Assignment", doc.assignment)
    assignment.db_set("bed", doc.to_bed)
    assignment.db_set("room", doc.to_room)
    assignment.db_set("building", to_building)

    recalculate_spatial(asg.room, asg.building)
    recalculate_spatial(doc.to_room, to_building)


def before_cancel(doc, method=None):
    asg = frappe.db.get_value(
        "Housing Assignment",
        doc.assignment,
        ["docstatus", "check_out_date", "bed"],
        as_dict=True,
        for_update=True,
    )
    if not asg or asg.docstatus != 1 or asg.check_out_date or asg.bed != doc.to_bed:
        frappe.throw(
            _("This transfer can no longer be reversed: the resident is no longer in Bed {0}.").format(
                doc.to_bed
            )
        )

    origin_status = frappe.db.get_value("Bed", doc.from_bed, "status", for_update=True)
    if origin_status != "Available":
        frappe.throw(
            _("This transfer can no longer be reversed: Bed {0} is no longer free ({1}).").format(
                doc.from_bed, _(origin_status or "")
            )
        )


def on_cancel(doc, method=None):
    from_room = frappe.db.get_value("Bed", doc.from_bed, "room")
    from_building = (
        frappe.db.get_value("Room", from_room, "building") if from_room else None
    )
    to_building = frappe.db.get_value("Room", doc.to_room, "building")

    frappe.db.set_value("Bed", doc.to_bed, "status", "Available")
    frappe.db.set_value("Bed", doc.from_bed, "status", "Occupied")

    assignment = frappe.get_doc("Housing Assignment", doc.assignment)
    assignment.db_set("bed", doc.from_bed)
    assignment.db_set("room", from_room)
    assignment.db_set("building", from_building)

    recalculate_spatial(doc.to_room, to_building)
    recalculate_spatial(from_room, from_building)
