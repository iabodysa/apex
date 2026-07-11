# Copyright (c) 2026, AFMCO and contributors
"""Seed the Logistay native Frappe Workflows from their shipped JSON definitions.

Frappe's ``bench migrate`` does NOT auto-import a ``Workflow`` from a module
folder (Workflow is not in ``frappe.model.sync.IMPORTABLE_DOCTYPES``), unlike
Web Form / Print Format / Notification. So the canonical definition is shipped
as a JSON under ``logistay/workflow/<name>/<name>.json`` (the design artifact and
single source of truth) and applied here, idempotently and existence-guarded,
exactly like the Salis / Habitat workflow seeds.

Reused by the app's ``after_install`` / ``after_migrate`` hooks and by
``patches/v1_x/seed_logistay_workflows.py`` so a fresh install gets the workflow
immediately while already-installed sites pick it up on migrate. Every step is
existence-guarded and skip-missing (the target DocType and every Workflow State
/ Workflow Action Master referenced), so running it twice - or on a partially
installed module - is safe and never aborts the migrate.

Seeds the TS Intake Source lifecycle Workflow (Pending -> Processed / Failed /
Skipped), driven by the existing ``status`` Select on TS Intake Source. No new
field: the workflow rides the field the ingestion engine already stamps.
"""

import json
import os

import frappe

from apex.apex_core.setup.seeders.workflow_seed_base import seed_one

# [#lg_wf_dirs]
_WORKFLOW_DIRS = [
    "ts_intake_source_workflow",
]

# [#lg_wf_style] state colours mirror the intake status indicators.
_STATE_STYLE = {
    "Pending": "Warning",
    "Processed": "Success",
    "Failed": "Danger",
    "Skipped": "Primary",
}


def _load_definition(dir_name):
    """Load a shipped Workflow JSON definition from logistay/workflow/<dir>/."""
    path = os.path.join(
        frappe.get_app_path("apex", "logistay", "workflow"),
        dir_name,
        dir_name + ".json",
    )
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def seed_logistay_workflows():
    """Create the Logistay native Workflows if absent. Idempotent + existence-
    guarded on the target DocType and every referenced state/action master -
    safe to re-run (install + every migrate)."""
    for dir_name in _WORKFLOW_DIRS:
        sp = "lg_wf_seed"
        frappe.db.savepoint(sp)
        try:
            definition = _load_definition(dir_name)
            seed_one(definition, _STATE_STYLE)
        except Exception:
            frappe.log_error(
                title=f"seed_logistay_workflows failed: {dir_name}",
                message=frappe.get_traceback(),
            )
            frappe.db.rollback(save_point=sp)
    frappe.db.commit()
