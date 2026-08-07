# Copyright (c) 2026, AFMCO and contributors
"""Seed the operational Auto Email Reports (disabled, Administrator placeholder)
on existing sites. Idempotent.

Swallowing the failure is safe here because the same seeder runs on EVERY migrate:
``habitat_auto_email_reports_seed.seed_auto_email_reports`` is listed in hooks.py
``after_migrate``. A run that silently did nothing is re-attempted by the next migrate,
so a stamped patch never becomes the last chance to create these records.
"""

import frappe

from apex.apex_core.setup.seeders.habitat_auto_email_reports_seed import seed_auto_email_reports


def execute():
    try:
        seed_auto_email_reports()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_auto_email_reports failed",
            message=frappe.get_traceback(),
        )
