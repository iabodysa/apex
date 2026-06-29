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
Assessment (all in the Habitat module) and Employee Deduction
Acknowledgment (Apex Core).
"""

import json
import os

import frappe

# (module_dir, workflow_dir) — the JSON lives at
# <app>/<module_dir>/workflow/<workflow_dir>/<workflow_dir>.json  [#hbwf01]
_WORKFLOWS = [
    ("habitat", "utility_bill_entry_workflow"),
    ("habitat", "subcontractor_service_contract_workflow"),
    ("habitat", "custody_damage_assessment_workflow"),
    ("habitat", "accommodation_lease_workflow"),
    ("apex_core", "employee_deduction_acknowledgment_workflow"),
]

# Mirror each DocType's status indicator colours on the desk Workflow widget.  [#hbwf02]
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
        frappe.get_app_path("apex_habitat", module_dir, "workflow"),
        workflow_dir,
        workflow_dir + ".json",
    )
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _ensure_workflow_state(state_name):
    """Create the Workflow State master record if absent (autoname = the name)."""
    if frappe.db.exists("Workflow State", state_name):
        return
    frappe.get_doc(
        {
            "doctype": "Workflow State",
            "workflow_state_name": state_name,
            "style": _STATE_STYLE.get(state_name, ""),
        }
    ).insert(ignore_permissions=True)  # audit-ok


def _ensure_workflow_action(action_name):
    """Create the Workflow Action Master record if absent (autoname = the name)."""
    if frappe.db.exists("Workflow Action Master", action_name):
        return
    frappe.get_doc(
        {
            "doctype": "Workflow Action Master",
            "workflow_action_name": action_name,
        }
    ).insert(ignore_permissions=True)  # audit-ok


def _seed_one(definition):
    """Apply a single Workflow definition idempotently. Returns True if the
    workflow now exists, False if it was skipped (e.g. document type missing)."""
    document_type = definition["document_type"]
    if not frappe.db.exists("DocType", document_type):
        return False  # [#hbwf03]

    for state in definition.get("states", []):
        _ensure_workflow_state(state["state"])
    for transition in definition.get("transitions", []):
        _ensure_workflow_state(transition["next_state"])
        _ensure_workflow_action(transition["action"])

    name = definition["name"]
    if frappe.db.exists("Workflow", name):
        # Keep an already-seeded workflow active if the definition is active.  [#hbwf04]
        if definition.get("is_active") and not frappe.db.get_value("Workflow", name, "is_active"):
            doc = frappe.get_doc("Workflow", name)
            doc.is_active = 1
            doc.save(ignore_permissions=True)  # audit-ok
        return True

    doc = frappe.new_doc("Workflow")
    doc.workflow_name = definition.get("workflow_name", name)
    doc.document_type = document_type
    doc.workflow_state_field = definition["workflow_state_field"]
    doc.is_active = definition.get("is_active", 1)
    doc.override_status = definition.get("override_status", 0)
    doc.send_email_alert = definition.get("send_email_alert", 0)

    for state in definition.get("states", []):
        doc.append(
            "states",
            {
                "state": state["state"],
                "doc_status": state.get("doc_status", "0"),
                "allow_edit": state.get("allow_edit"),
                "is_optional_state": state.get("is_optional_state", 0),
            },
        )
    for transition in definition.get("transitions", []):
        doc.append(
            "transitions",
            {
                "state": transition["state"],
                "action": transition["action"],
                "next_state": transition["next_state"],
                "allowed": transition.get("allowed"),
                "allow_self_approval": transition.get("allow_self_approval", 1),
                "condition": transition.get("condition") or "",
            },
        )

    doc.name = name
    doc.flags.name_set = True
    doc.insert(ignore_permissions=True)  # audit-ok
    return True


def seed_habitat_workflows():
    """Create the Habitat / Apex Core approval Workflows if absent. Idempotent +
    existence-guarded on the target DocType and every referenced state/action
    master — safe to re-run (install + every migrate)."""
    for module_dir, workflow_dir in _WORKFLOWS:
        sp = "habitat_wf_seed"
        frappe.db.savepoint(sp)
        try:
            definition = _load_definition(module_dir, workflow_dir)
            _seed_one(definition)
        except Exception:
            # One bad workflow must never abort the whole migrate.  [#hbwf05]
            frappe.log_error(
                title=f"seed_habitat_workflows failed: {workflow_dir}",
                message=frappe.get_traceback(),
            )
            frappe.db.rollback(save_point=sp)
    frappe.db.commit()
