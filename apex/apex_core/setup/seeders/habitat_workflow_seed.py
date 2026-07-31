# Copyright (c) 2026, AFMCO and contributors
"""Seed the Habitat / Apex Core approval Workflows from their shipped JSON.

Frappe's ``bench migrate`` does NOT auto-import a ``Workflow`` from a module
folder (Workflow is not in ``frappe.model.sync.IMPORTABLE_DOCTYPES``), so a
``*/workflow/<name>/<name>.json`` shipped on disk is a design artifact only and
never reaches the database on its own. Without this seeder the five approval
workflows below would never exist on any site. This mirrors
``salis_workflow_seed`` for the Habitat / Apex Core side.

Each workflow is applied idempotently and existence-guarded on the target
DocType plus every referenced Workflow State and Workflow Action Master, so
running it twice — or on a partially installed app — is safe and never aborts
the migrate. Segregation of Duties is carried by the shipped definitions
themselves (``allow_self_approval = 0`` on the Approve transition), never
re-implemented here.

Seeds: Utility Bill Entry, Subcontractor Service Contract, Custody Damage
Assessment, and Accommodation Lease (all in the Habitat module).
"""

import json
import os

import frappe

from apex.apex_core.setup.seeders.workflow_seed_base import seed_one

# [#t8tohs]
_WORKFLOWS = [
    ("habitat", "utility_bill_entry_workflow"),
    ("habitat", "subcontractor_service_contract_workflow"),
    ("habitat", "custody_damage_assessment_workflow"),
    ("habitat", "lease_workflow"),
]

# [#dy27i5]
_STATE_STYLE = {
    "Draft": "Primary",
    "Pending": "Warning",
    "Pending Approval": "Warning",
    "Approved": "Success",
    "Active": "Success",
    "Rejected": "Danger",
}


def _load_definition(module_dir, workflow_dir):
    """Load a shipped Workflow JSON from <module_dir>/workflow/<workflow_dir>/."""
    path = os.path.join(
        frappe.get_app_path("apex", module_dir, "workflow"),
        workflow_dir,
        workflow_dir + ".json",
    )
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def seed_habitat_workflows():
    """Create the Habitat / Apex Core approval Workflows if absent. Idempotent +
    existence-guarded on the target DocType and every referenced state/action
    master — safe to re-run (install + every migrate)."""
    for module_dir, workflow_dir in _WORKFLOWS:
        sp = "habitat_wf_seed"
        frappe.db.savepoint(sp)
        try:
            definition = _load_definition(module_dir, workflow_dir)
            seed_one(definition, _STATE_STYLE)
        except Exception:
            # [#b9mw4c]
            frappe.log_error(
                title=f"seed_habitat_workflows failed: {workflow_dir}",
                message=frappe.get_traceback(),
            )
            frappe.db.rollback(save_point=sp)
    frappe.db.commit()
