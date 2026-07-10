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


def _apply_definition(doc, definition, document_type):
    """Write the JSON definition's header + states + transitions onto ``doc``
    (replacing any existing child rows), so create and reconcile share one path."""
    name = definition["name"]
    doc.workflow_name = definition.get("workflow_name", name)
    doc.document_type = document_type
    doc.workflow_state_field = definition["workflow_state_field"]
    doc.is_active = definition.get("is_active", 1)
    doc.override_status = definition.get("override_status", 0)
    doc.send_email_alert = definition.get("send_email_alert", 0)

    doc.states = []
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
    doc.transitions = []
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


def _seed_one(definition):
    """Apply a single Workflow definition idempotently. Returns True if the
    workflow now exists, False if it was skipped (e.g. document type missing)."""
    document_type = definition["document_type"]
    if not frappe.db.exists("DocType", document_type):
        return False  # [#lg_wf_skip] target DocType not installed yet

    for state in definition.get("states", []):
        _ensure_workflow_state(state["state"])
    for transition in definition.get("transitions", []):
        _ensure_workflow_state(transition["next_state"])
        _ensure_workflow_action(transition["action"])

    name = definition["name"]
    if frappe.db.exists("Workflow", name):
        doc = frappe.get_doc("Workflow", name)
        _apply_definition(doc, definition, document_type)
        doc.save(ignore_permissions=True)  # audit-ok
        return True

    doc = frappe.new_doc("Workflow")
    _apply_definition(doc, definition, document_type)
    doc.name = name
    doc.flags.name_set = True
    doc.insert(ignore_permissions=True)  # audit-ok
    return True


def seed_logistay_workflows():
    """Create the Logistay native Workflows if absent. Idempotent + existence-
    guarded on the target DocType and every referenced state/action master -
    safe to re-run (install + every migrate)."""
    for dir_name in _WORKFLOW_DIRS:
        sp = "lg_wf_seed"
        frappe.db.savepoint(sp)
        try:
            definition = _load_definition(dir_name)
            _seed_one(definition)
        except Exception:
            frappe.log_error(
                title=f"seed_logistay_workflows failed: {dir_name}",
                message=frappe.get_traceback(),
            )
            frappe.db.rollback(save_point=sp)
    frappe.db.commit()
