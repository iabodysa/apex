"""Seed the v0.8.6 idle-resident-reported Notification on existing sites. Idempotent;
creates only the new one, disabled by default.
"""

import frappe

from apex_habitat.habitat.notifications_seed import seed_operational_notifications


def execute():
    try:
        seed_operational_notifications()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_idle_resident_notification failed",
            message=frappe.get_traceback(),
        )
