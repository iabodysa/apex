# Copyright (c) 2026, AFMCO and contributors
"""Seed the Salis Auto Email Reports on existing sites.

The Salis Email Templates moved to the data-driven loader
``apex.apex_core.setup.seed.seed_all`` (create-only JSON under
``apex_core/setup/data/salis/email_template.json``) in the seed consolidation
(M-10/M-11). Auto Email Reports stay a seeder (runtime recipient fields, not
externalised to JSON), so this patch keeps replaying that one idempotent step;
already-installed sites pick up newly-added reports on migrate.

Swallowing the failure is safe here because the seeder it calls runs on EVERY migrate:
``salis_auto_email_reports_seed.seed_salis_auto_email_reports`` is listed in hooks.py
``after_migrate``. A run that silently did nothing is re-attempted by the next migrate,
so the stamped patch is never the last chance to create these records.
"""

import frappe

from apex.apex_core.setup.seeders.salis_auto_email_reports_seed import seed_salis_auto_email_reports


def execute():
    try:
        seed_salis_auto_email_reports()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_salis_communications failed: seed_salis_auto_email_reports",
            message=frappe.get_traceback(),
        )
