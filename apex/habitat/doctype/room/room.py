# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class Room(Document):
    pass


@frappe.whitelist(methods=["POST"])
def toggle_service(room: str) -> str:
    doc = frappe.get_doc("Room", room)
    doc.check_permission("write")
    new_status = "Ready" if doc.readiness_status == "Out of Service" else "Out of Service"
    if new_status == "Out of Service":
        occupants = frappe.db.count(
            "Housing Assignment",
            {"room": room, "docstatus": 1, "check_out_date": ["is", "not set"]},
        )
        if occupants:
            frappe.throw(
                _("Room {0} has {1} current occupant(s). Check them out before deactivating it.").format(room, occupants)
            )
    doc.db_set("readiness_status", new_status)
    return new_status
