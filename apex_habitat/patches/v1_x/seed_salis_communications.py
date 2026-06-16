"""Seed the Salis Auto Email Reports on existing sites.

The Salis Email Templates moved to the data-driven loader
``apex_habitat.apex_core.setup.seed.seed_all`` (create-only JSON under
``apex_core/setup/data/salis/email_template.json``) in the seed consolidation
(M-10/M-11). Auto Email Reports stay a seeder (runtime recipient fields, not
externalised to JSON), so this patch keeps replaying that one idempotent step;
already-installed sites pick up newly-added reports on migrate.
"""

import frappe

from apex_habitat.apex_core.setup.seeders.salis_auto_email_reports_seed import seed_salis_auto_email_reports


def execute():
    try:
        seed_salis_auto_email_reports()
    except Exception:
        # [#r786tj]
        frappe.db.rollback()
        frappe.log_error(
            title="seed_salis_communications failed: seed_salis_auto_email_reports",
            message=frappe.get_traceback(),
        )
