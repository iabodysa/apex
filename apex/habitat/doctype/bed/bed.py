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
    deactivated; the resident must be checked out first. Returns the new status."""
    doc = frappe.get_doc("Bed", bed, for_update=True)
    doc.check_permission("write")
    if doc.status == "Occupied":
        frappe.throw(_("Bed {0} is occupied. Check the resident out before deactivating it.").format(bed))
    new_status = "Available" if doc.status == "Out of Service" else "Out of Service"
    doc.db_set("status", new_status)
    return new_status
