# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import today


@frappe.whitelist(methods=["POST"])
def transfer_occupant(source_bed, target_bed, transfer_date=None, reason=None):
    frappe.has_permission("Room Bed Transfer", "create", throw=True)
    frappe.has_permission("Room Bed Transfer", "submit", throw=True)

    if not source_bed or not target_bed:
        frappe.throw(_("Both a source bed and a target bed are required."))
    if source_bed == target_bed:
        frappe.throw(_("Source and target beds must be different."))

    assignment = frappe.db.get_value(
        "Housing Assignment",
        {"bed": source_bed, "docstatus": 1, "check_out_date": ["is", "not set"]},
        "name",
    )
    if not assignment:
        frappe.throw(_("Source bed has no active resident to transfer."))

    target_room, target_building = frappe.db.get_value(
        "Bed", target_bed, ["room", "building"]
    )
    if not target_room or not target_building:
        frappe.throw(_("Target bed {0} is not linked to a room and building.").format(target_bed))

    doc = frappe.get_doc(
        {
            "doctype": "Room Bed Transfer",
            "assignment": assignment,
            "to_room": target_room,
            "to_bed": target_bed,
            "transfer_date": transfer_date or today(),
            "reason": reason,
        }
    )
    doc.insert(ignore_permissions=False)
    doc.submit()
    return {"transfer": doc.name, "source_bed": source_bed, "target_bed": target_bed}
