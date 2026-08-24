# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.portal_live import notify_building


class Bed(Document):
    pass


@frappe.whitelist(methods=["POST"])
def toggle_service(bed: str) -> str:
    doc = frappe.get_doc("Bed", bed, for_update=True)
    doc.check_permission("write")
    if doc.status == "Occupied":
        frappe.throw(_("Bed {0} is occupied. Check the resident out before deactivating it.").format(bed))
    new_status = "Available" if doc.status == "Out of Service" else "Out of Service"
    doc.db_set("status", new_status)
    notify_building(doc.building)
    return new_status
