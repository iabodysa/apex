# Copyright (c) 2026, AFMCO and contributors
"""Room Bed Transfer controller.

In-place move of an active occupant from one bed to another without closing
and re-opening the Accommodation Assignment.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.apex_core.utils.party_link import sync_party_employee


class RoomBedTransfer(Document):
    pass


def validate(doc, method=None):
    sync_party_employee(doc, derive_from="assignment")

    if not doc.to_bed or not doc.to_room:
        return  # [#h7vrny]

    bed_status = frappe.db.get_value("Bed", doc.to_bed, "status")
    if bed_status == "Out of Service":
        frappe.throw(_("Target Bed {0} is Out of Service.").format(doc.to_bed))
    elif bed_status == "Occupied":
        frappe.throw(_("Target bed is already occupied."))

    # [#fylvr5]
    bed_room = frappe.db.get_value("Bed", doc.to_bed, "room")
    if bed_room is not None and bed_room != doc.to_room:
        frappe.throw(_("Target Bed {0} does not belong to Room {1}").format(doc.to_bed, doc.to_room))

    # [#c91vez] An unset Link returns None (not ""), so the old `is not None and not`
    # guard never fired — a room with no building slipped through. `not to_building`
    # catches both None and an empty value, so the integrity check actually runs.
    to_building = frappe.db.get_value("Room", doc.to_room, "building")
    if not to_building:
        frappe.throw(_("Target Room {0} is not associated with any Building.").format(doc.to_room))


def on_submit(doc, method=None):
    # [#lfwp8g]
    asg = frappe.db.get_value(
        "Housing Assignment", doc.assignment, ["docstatus", "check_out_date"], as_dict=True
    )
    if not asg or asg.docstatus != 1 or asg.check_out_date:
        frappe.throw(_("This transfer needs an active (checked-in) assignment to move."))

    # [#hzjmc4]
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


def on_cancel(doc, method=None):
    # Inverse of on_submit: free the target bed, re-occupy the original, and move the
    # assignment back to where it was. The original room/building are derived from
    # from_bed (the transfer stores no from_room/from_building of its own).
    frappe.db.set_value("Bed", doc.to_bed, "status", "Available")
    frappe.db.set_value("Bed", doc.from_bed, "status", "Occupied")

    from_room = frappe.db.get_value("Bed", doc.from_bed, "room")
    from_building = (
        frappe.db.get_value("Room", from_room, "building") if from_room else None
    )
    # Only revert the assignment if it still points at this transfer's target; a later
    # transfer or check-out may have moved it on, and we must not clobber that state.
    assignment = frappe.get_doc("Housing Assignment", doc.assignment)
    if assignment.bed == doc.to_bed:
        assignment.db_set("bed", doc.from_bed)
        assignment.db_set("room", from_room)
        assignment.db_set("building", from_building)
