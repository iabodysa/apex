# Copyright (c) 2026, AFMCO and contributors
"""Shared engine for the per-module Workflow seeders.

Frappe's ``bench migrate`` does NOT auto-import a ``Workflow`` from a module
folder (Workflow is not in ``frappe.model.sync.IMPORTABLE_DOCTYPES``), so each
module ships its Workflows as ``<module>/workflow/<name>/<name>.json`` design
artifacts and applies them here, idempotently and existence-guarded. The module
seeders (``habitat_workflow_seed`` / ``salis_workflow_seed``) reuse the
primitives below so the create/reconcile logic lives in exactly one place; each
module keeps only its own workflow list, state-colour map, and definition
loader.
"""

import frappe


def ensure_workflow_state(state_name, style_map):
    """Create the Workflow State master record if absent (autoname = the name)."""
    if frappe.db.exists("Workflow State", state_name):
        return
    frappe.get_doc(
        {
            "doctype": "Workflow State",
            "workflow_state_name": state_name,
            "style": style_map.get(state_name, ""),
        }
    ).insert(ignore_permissions=True)  # audit-ok


def ensure_workflow_action(action_name):
    """Create the Workflow Action Master record if absent (autoname = the name)."""
    if frappe.db.exists("Workflow Action Master", action_name):
        return
    frappe.get_doc(
        {
            "doctype": "Workflow Action Master",
            "workflow_action_name": action_name,
        }
    ).insert(ignore_permissions=True)  # audit-ok


def apply_definition(doc, definition, document_type):
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


def seed_one(definition, style_map):
    """Apply a single Workflow definition idempotently. Returns True if the
    workflow now exists, False if it was skipped (e.g. document type missing).

    Both the create and the reconcile path go through :func:`apply_definition`,
    so an already-present Workflow is re-aligned with the shipped JSON on every
    migrate."""
    document_type = definition["document_type"]
    if not frappe.db.exists("DocType", document_type):
        return False

    for state in definition.get("states", []):
        ensure_workflow_state(state["state"], style_map)
    for transition in definition.get("transitions", []):
        ensure_workflow_state(transition["next_state"], style_map)
        ensure_workflow_action(transition["action"])

    name = definition["name"]
    if frappe.db.exists("Workflow", name):
        doc = frappe.get_doc("Workflow", name)
        apply_definition(doc, definition, document_type)
        doc.save(ignore_permissions=True)  # audit-ok
        return True

    doc = frappe.new_doc("Workflow")
    apply_definition(doc, definition, document_type)
    doc.name = name
    doc.flags.name_set = True
    doc.insert(ignore_permissions=True)  # audit-ok
    return True
