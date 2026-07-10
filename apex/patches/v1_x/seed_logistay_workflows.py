# Copyright (c) 2026, AFMCO and contributors
"""Seed the Logistay native Frappe Workflow (TS Intake Source lifecycle).

Mirrors the Salis / Habitat workflow seed patches: the seed logic lives in the
idempotent, existence-guarded ``apex_core/setup/seeders/logistay_workflow_seed``
module (single source of truth). This patch - and the app's ``after_install`` /
``after_migrate`` hooks - reuse that same function, so a fresh install gets the
workflow immediately while already-installed sites pick it up on migrate.

Frappe does not auto-import a Workflow from a module folder (Workflow is not in
``frappe.model.sync.IMPORTABLE_DOCTYPES``), so this seed is the install path.

PERMANENT (keep, do NOT prune): seeds a DISTINCT record set (Workflow + its
Workflow State / Workflow Action Master masters) and fresh installs must replay
it. Idempotent (also called from the hooks), not redundant.
"""

import frappe

from apex.apex_core.setup.seeders.logistay_workflow_seed import seed_logistay_workflows


def execute():
    try:
        seed_logistay_workflows()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_logistay_workflows patch failed",
            message=frappe.get_traceback(),
        )
