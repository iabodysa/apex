# Copyright (c) 2026, afmcoltd
"""Accommodation Bed controller. Smallest atomic spatial unit."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class Bed(Document):
    pass


@frappe.whitelist(methods=["POST"])
def toggle_service(bed: str) -> str:
    """Activate / deactivate a bed by flipping its existing ``status`` between Available
    and Out of Service — the value the assignment and room/bed-transfer guards already
    honor, so no parallel "active" flag is introduced. An Occupied bed cannot be
    deactivated; the resident must be checked out first. Returns the new status.

    This is the one bed-state change that never touches occupancy, so it never reaches
    the ``recalculate_building_occupancy`` choke point that notifies the building's watchers.
    It publishes the framework's own ``doc_update`` event directly, on the Building doc room,
    so the portal needs one listener for both paths rather than a bed-specific one."""
    doc = frappe.get_doc("Bed", bed, for_update=True)
    doc.check_permission("write")
    if doc.status == "Occupied":
        frappe.throw(_("Bed {0} is occupied. Check the resident out before deactivating it.").format(bed))
    new_status = "Available" if doc.status == "Out of Service" else "Out of Service"
    doc.db_set("status", new_status)
    frappe.publish_realtime(
        "doc_update",
        {"doctype": "Building", "name": doc.building},
        doctype="Building",
        docname=doc.building,
        after_commit=True,
    )
    return new_status
