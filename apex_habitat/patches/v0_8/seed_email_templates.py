"""Seed the reusable Email Templates on existing sites. Idempotent."""

import frappe

from apex_habitat.habitat.email_templates_seed import seed_email_templates


def execute():
    try:
        seed_email_templates()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_email_templates failed",
            message=frappe.get_traceback(),
        )
