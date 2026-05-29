"""Seed the Salis native Frappe Workflows from their shipped JSON definitions.

Frappe's ``bench migrate`` does NOT auto-import a ``Workflow`` from a module
folder (Workflow is not in ``frappe.model.sync.IMPORTABLE_DOCTYPES``), unlike
Web Form / Print Format / Notification. So the canonical definition is shipped
as a JSON under ``salis/workflow/<name>/<name>.json`` (the design artifact and
single source of truth) and applied here, idempotently and existence-guarded,
exactly like the other Salis seeds (notifications / kanban / assignment rules).

This module is reused by the app's ``after_install`` / ``after_migrate`` hooks
and by ``patches/v1_x/seed_salis_workflows.py`` so a fresh install gets the
workflows immediately while already-installed sites pick them up on migrate.
Every step is existence-guarded and skip-missing (the target DocType, every
Workflow State and Workflow Action Master referenced), so running it twice — or
on a partially installed module — is safe and never aborts the migrate.

Seeds the Salis Workflow Spine: Transport Request, Rental Settlement, Driver
Clearance, Salis Payment Request, Support Ticket and Sponsorship Transfer Case.
Each one is applied independently, so a missing target DocType only skips that
one workflow.

Colours for the workflow states mirror each DocType's own status indicator
colours so the desk Workflow widget matches the list view.
"""

import json
import os

import frappe

# Workflow definitions to seed: the folder name under salis/workflow/.
_WORKFLOW_DIRS = [
    "transport_request_workflow",
    "rental_settlement_workflow",
    "driver_clearance_workflow",
    "salis_payment_request_workflow",
    "support_ticket_workflow",
    "sponsorship_transfer_case_workflow",
]

# State -> indicator style, mirroring each DocType's status indicator colours so
# the Workflow widget matches the list/state colours. Shared across the seeded
# workflows; a state name reused by more than one workflow keeps the same style.
_STATE_STYLE = {
    # Transport Request
    "New": "Primary",
    "Validated": "Primary",
    "Approved": "Primary",
    "Scheduled": "Warning",
    "Fulfilled": "Success",
    "Rejected": "Danger",
    "Cancelled": "Danger",
    # Rental Settlement
    "Draft": "Primary",
    "Reconciled": "Warning",
    "Disputed": "Danger",
    "Paid": "Success",
    # Driver Clearance
    "Open": "Warning",
    "In Progress": "Primary",
    "Cleared": "Success",
    "Blocked": "Danger",
    # Salis Payment Request (Draft / Paid / Rejected / Cancelled reuse the above)
    "Pending Finance": "Warning",
    "Approved by Finance": "Primary",
    # Support Ticket (New / In Progress / Cancelled reuse the styles above)
    "Waiting": "Warning",
    "Resolved": "Primary",
    "Closed": "Success",
    # Sponsorship Transfer Case (Open / In Progress / Cancelled reuse the above)
    "Completed": "Success",
}


def _load_definition(dir_name):
    """Load a shipped Workflow JSON definition from salis/workflow/<dir>/."""
    path = os.path.join(
        os.path.dirname(__file__), "workflow", dir_name, dir_name + ".json"
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
        return False  # module not migrated yet — skip silently

    # The masters the child rows Link to must exist before the Workflow is saved,
    # otherwise the Link validation raises and aborts.
    for state in definition.get("states", []):
        _ensure_workflow_state(state["state"])
    for transition in definition.get("transitions", []):
        _ensure_workflow_state(transition["next_state"])
        _ensure_workflow_action(transition["action"])

    name = definition["name"]
    if frappe.db.exists("Workflow", name):
        # Already present — leave the admin's copy untouched (it may have been
        # tuned on-site). Just make sure exactly this one is the active workflow
        # for the document type.
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

    # Frappe's Workflow autoname is by workflow_name; force the documented name so
    # the existence guard above is stable across re-runs.
    doc.name = name
    doc.flags.name_set = True
    doc.insert(ignore_permissions=True)  # audit-ok
    return True


def seed_salis_workflows():
    """Create the Salis native Workflows if absent. Idempotent + existence-guarded
    on the target DocType and every referenced state/action master — safe to
    re-run (install + every migrate)."""
    for dir_name in _WORKFLOW_DIRS:
        try:
            definition = _load_definition(dir_name)
            _seed_one(definition)
        except Exception:
            # A seed must NEVER crash install/migrate — log and continue.
            frappe.db.rollback()
            frappe.log_error(
                title=f"seed_salis_workflows failed: {dir_name}",
                message=frappe.get_traceback(),
            )
    frappe.db.commit()
