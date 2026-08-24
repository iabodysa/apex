# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.realtime import get_doctype_room


def notify_building(building: str | None) -> bool:
    if not building:
        return False
    frappe.publish_realtime(
        "doc_update",
        {"doctype": "Building", "name": building},
        doctype="Building",
        docname=building,
        after_commit=True,
    )
    return True


def notify_doctype(doctype: str, event: str, message: dict | None = None) -> bool:
    if not doctype:
        return False
    frappe.publish_realtime(
        event,
        message or {},
        room=get_doctype_room(doctype),
        after_commit=True,
    )
    return True
