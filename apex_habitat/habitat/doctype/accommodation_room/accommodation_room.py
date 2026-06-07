"""Accommodation Room controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class AccommodationRoom(Document):
    pass


@frappe.whitelist(methods=["POST"])
def toggle_service(room: str) -> str:
    """Activate / deactivate a room by flipping ``readiness_status`` between Ready and Out
    of Service — the value the assignment guard already honors, so no parallel "active"
    flag is introduced. Deactivating only blocks NEW assignments; existing residents are
    untouched. Returns the new readiness_status."""
    doc = frappe.get_doc("Accommodation Room", room)
    doc.check_permission("write")
    new_status = "Ready" if doc.readiness_status == "Out of Service" else "Out of Service"
    doc.db_set("readiness_status", new_status)
    return new_status
