# Copyright (c) 2026, afmcoltd
"""Room Bed Transfer controller.

In-place move of an active occupant from one bed to another WITHIN ONE BUILDING,
without closing and re-opening the Housing Assignment.

Why the rule is a REJECTION and not a re-derivation: the move re-points the live
assignment with ``db_set``, which writes straight to the row and never runs
``Housing Assignment.validate()``. That validate is what derives ``cost_center``
from the building (and its Company), and ``housing_allowance_suspended`` is only
ever set in the assignment's own ``on_submit``. A building change made here would
therefore carry the OLD building's cost centre and allowance state into the NEW
building's Company. Housing Checkout plus a fresh check-in is the path that runs
those effects, so a cross-building move goes there.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.party_link import sync_party_employee
from apex.habitat.doctype.housing_assignment.housing_assignment import recalculate_spatial


class RoomBedTransfer(Document):
    """Preconditions run in ``before_*``, side effects in ``on_*``.

    """

    def before_submit(self):
        """Runs the module-level check that the source assignment is active on the expected bed."""
        before_submit(self)

    def before_cancel(self):
        """Runs the module-level check that the resident is still in the target bed before cancel."""
        before_cancel(self)


def _source_building(doc):
    """Building the resident is being moved OUT of, or None.

    """
    building = None
    if doc.assignment:
        building = frappe.db.get_value("Housing Assignment", doc.assignment, "building")
    if not building and doc.from_bed:
        building = frappe.db.get_value("Bed", doc.from_bed, "building")
    return building


def validate(doc, method=None):
    """Blocks a transfer to an unavailable bed, a bed outside the target room, or across buildings."""
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
    """Blocks submission unless the source assignment is active, checked in, and on the origin bed."""
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
    """Moves the bed under lock, re-points the assignment, and recalculates occupancy at both ends."""
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
    """Refuse rather than half-reverse.

    The reversal below flips both bed statuses. Doing that while the resident has
    since moved on — or checked out — re-occupies ``from_bed`` for somebody who is
    not in it, a phantom occupancy no report can explain. The old code guarded only
    the assignment re-point and flipped the beds regardless.

    Locked like ``before_submit``, and for the same reason: the check and the
    reversal it authorises must see the same assignment row.
    """
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
    """Reverses the bed swap, re-points the assignment to the origin, and recalculates occupancy."""
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
