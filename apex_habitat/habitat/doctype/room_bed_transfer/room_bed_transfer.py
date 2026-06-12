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
        return  # Mandatory check will catch missing fields

    bed_status = frappe.db.get_value("Accommodation Bed", doc.to_bed, "status")
    if bed_status == "Out of Service":
        frappe.throw(_("Target Bed {0} is Out of Service.").format(doc.to_bed))
    elif bed_status == "Occupied":
        frappe.throw(_("Target bed is already occupied."))

    # Validate target bed belongs to target room
    bed_room = frappe.db.get_value("Accommodation Bed", doc.to_bed, "room")
    if bed_room is not None and bed_room != doc.to_room:
        frappe.throw(_("Target Bed {0} does not belong to Room {1}").format(doc.to_bed, doc.to_room))

    # Validate target room is associated with a building. A room with no
    # building would null out the assignment's building at on_submit, so reject
    # it here. get_value returns None (not "") when the Link is unset.
    to_building = frappe.db.get_value("Accommodation Room", doc.to_room, "building")
    if not to_building:
        frappe.throw(_("Target Room {0} is not associated with any Building.").format(doc.to_room))


def on_submit(doc, method=None):
    # The occupant being moved must be a CURRENT resident: the linked assignment must be
    # submitted and not yet checked out. Guards against executing a transfer for a
    # closed/cancelled stay. (Checked at submit — the point the move actually applies.)
    asg = frappe.db.get_value(
        "Accommodation Assignment", doc.assignment, ["docstatus", "check_out_date"], as_dict=True
    )
    if not asg or asg.docstatus != 1 or asg.check_out_date:
        frappe.throw(_("This transfer needs an active (checked-in) assignment to move."))

    # Concurrency guard: lock the target bed row (SELECT ... FOR UPDATE) and
    # re-check availability inside the transaction so two simultaneous transfers
    # (e.g. rapid drag-drops on the Transfer Board) cannot both claim it. Mirrors
    # the Accommodation Assignment bed lock.
    locked_status = frappe.db.get_value("Accommodation Bed", doc.to_bed, "status", for_update=True)
    if locked_status == "Out of Service":
        frappe.throw(_("Target Bed {0} is Out of Service.").format(doc.to_bed))
    if locked_status == "Occupied":
        frappe.throw(_("Target bed is already occupied."))

    frappe.db.set_value("Accommodation Bed", doc.from_bed, "status", "Available")
    frappe.db.set_value("Accommodation Bed", doc.to_bed, "status", "Occupied")
    to_building = frappe.db.get_value("Accommodation Room", doc.to_room, "building")
    assignment = frappe.get_doc("Accommodation Assignment", doc.assignment)
    assignment.db_set("bed", doc.to_bed)
    assignment.db_set("room", doc.to_room)
    assignment.db_set("building", to_building)


def on_cancel(doc, method=None):
    frappe.db.set_value("Accommodation Bed", doc.to_bed, "status", "Available")
    frappe.db.set_value("Accommodation Bed", doc.from_bed, "status", "Occupied")
