"""Seed the Salis communication artifacts: Email Templates and Auto Email Reports.

Mirrors the Habitat pattern (``patches/v0_8/seed_email_templates`` /
``seed_auto_email_reports`` -> module seeds): the seed logic lives in the
idempotent, existence-guarded ``salis/email_templates_seed.py`` and
``salis/auto_email_reports_seed.py`` modules (single source of truth). This
patch — and the app's ``after_install`` / ``after_migrate`` hooks — reuse those
same functions, so a fresh install gets the artifacts immediately while
already-installed sites pick them up on migrate.

The matching Salis Module Onboarding ("Salis Go-Live") and its Onboarding Steps
are standard module files under ``salis/module_onboarding/`` and
``salis/onboarding_step/`` — bench migrate imports them automatically, so they
need no patch step here.

PERMANENT (keep, do NOT prune): each function seeds DISTINCT records and fresh
installs must replay it. All are idempotent (also called from the hooks), not
redundant. Each step is independently wrapped so a partially installed module
never aborts the migrate or the surrounding Habitat/Salis seeds.
"""

import frappe

from apex_habitat.salis.email_templates_seed import seed_salis_email_templates
from apex_habitat.salis.auto_email_reports_seed import seed_salis_auto_email_reports


def execute():
    for step in (
        seed_salis_email_templates,
        seed_salis_auto_email_reports,
    ):
        try:
            step()
        except Exception:
            # A seed must NEVER crash install/migrate — log and continue.
            frappe.db.rollback()
            frappe.log_error(
                title=f"seed_salis_communications failed: {step.__name__}",
                message=frappe.get_traceback(),
            )
