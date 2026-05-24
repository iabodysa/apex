"""Habitat Operations Alert controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class HabitatOperationsAlert(Document):
    pass


def create_alert(
    alert_type: str,
    message: str,
    severity: str = "Warning",
    building: str | None = None,
    source_doctype: str | None = None,
    source_name: str | None = None,
) -> None:
    """Create a Habitat Operations Alert record.

    Called by scheduler tasks to surface warnings in the Frappe desk
    instead of writing only to logger.
    """
    try:
        doc = frappe.get_doc({
            "doctype": "Habitat Operations Alert",
            "alert_type": alert_type,
            "severity": severity,
            "building": building,
            "message": message,
            "source_doctype": source_doctype,
            "source_name": source_name,
            "is_resolved": 0,
        })
        doc.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title="Failed to create Habitat Operations Alert",
            message=frappe.get_traceback(),
        )
