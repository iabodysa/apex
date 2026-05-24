"""Seed the native operational Notification records on existing sites (part of
the move away from the custom Habitat Operations Alert). Idempotent; the
Notifications are created disabled so they don't send until an admin enables them.
"""

import frappe
from apex_habitat.habitat.notifications_seed import seed_operational_notifications


def execute():
    try:
        seed_operational_notifications()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_operational_notifications failed",
            message=frappe.get_traceback(),
        )
