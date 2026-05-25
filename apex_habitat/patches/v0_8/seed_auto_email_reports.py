"""Seed the operational Auto Email Reports (disabled, Administrator placeholder)
on existing sites. Idempotent.
"""

import frappe

from apex_habitat.habitat.auto_email_reports_seed import seed_auto_email_reports


def execute():
    try:
        seed_auto_email_reports()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_auto_email_reports failed",
            message=frappe.get_traceback(),
        )
