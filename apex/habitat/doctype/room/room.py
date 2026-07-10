# Copyright (c) 2026, AFMCO and contributors
"""Accommodation Room controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class Room(Document):
    pass


@frappe.whitelist(methods=["POST"])
def toggle_service(room: str) -> str:
    """Activate / deactivate a room by flipping ``readiness_status`` between Ready and Out
    of Service — the value the assignment guard already honors, so no parallel "active"
    flag is introduced. A room with current occupants cannot be deactivated: relocate or
    check them out first, consistent with the bed rule (no "occupied + out of service"
    state). Returns the new readiness_status."""
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
