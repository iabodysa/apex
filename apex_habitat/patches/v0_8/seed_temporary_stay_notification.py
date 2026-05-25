"""Seed the v0.8.5 temporary-stay-ending Notification on existing sites. Idempotent;
skips the Notifications already present and creates only the new one, disabled.
"""

import frappe

from apex_habitat.habitat.notifications_seed import seed_operational_notifications


def execute():
    try:
        seed_operational_notifications()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_temporary_stay_notification failed",
            message=frappe.get_traceback(),
        )
