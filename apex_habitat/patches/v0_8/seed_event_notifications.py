"""Seed the v0.8.3 event-based Notifications (assignment/new/submit) on existing
sites. Idempotent; the seed skips the four expiry Notifications already present
and creates only the new ones, disabled by default.
"""

import frappe

from apex_habitat.habitat.notifications_seed import seed_operational_notifications


def execute():
    try:
        seed_operational_notifications()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_event_notifications failed",
            message=frappe.get_traceback(),
        )
