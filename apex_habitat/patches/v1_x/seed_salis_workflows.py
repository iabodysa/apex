# Copyright (c) 2026, AFMCO and contributors
"""Seed the Salis native Frappe Workflows (Transport Request, Rental Settlement,
Driver Clearance, Salis Payment Request, Support Ticket, Sponsorship Transfer
Case, Fuel Request — the Workflow Spine).

Mirrors the other Salis seed patches: the seed logic lives in the idempotent,
existence-guarded ``apex_core/setup/seeders/salis_workflow_seed.py`` module
(single source of truth).
This patch — and the app's ``after_install`` / ``after_migrate`` hooks — reuse
that same function, so a fresh install gets the workflows immediately while
already-installed sites pick them up on migrate.

Frappe does not auto-import a Workflow from a module folder (Workflow is not in
``frappe.model.sync.IMPORTABLE_DOCTYPES``), so this seed is the install path.

PERMANENT (keep, do NOT prune): seeds a DISTINCT record set (Workflow + its
Workflow State / Workflow Action Master masters) and fresh installs must replay
it. Idempotent (also called from the hooks), not redundant.
"""

import frappe

from apex_habitat.apex_core.setup.seeders.salis_workflow_seed import seed_salis_workflows


def execute():
    try:
        seed_salis_workflows()
    except Exception:
        # [#r786tj]
        frappe.db.rollback()
        frappe.log_error(
            title="seed_salis_workflows patch failed",
            message=frappe.get_traceback(),
        )
