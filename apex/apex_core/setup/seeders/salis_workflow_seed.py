# Copyright (c) 2026, AFMCO and contributors
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
Clearance, Salis Payment Request, Support Ticket, Fuel Request, Fuel Claim,
Fuel Exception Case and Dispatch Trip. Each one is applied independently, so a
missing target DocType only skips that one workflow.

Colours for the workflow states mirror each DocType's own status indicator
colours so the desk Workflow widget matches the list view.
"""

import json
import os

import frappe

from apex.apex_core.setup.seeders.workflow_seed_base import seed_one

# [#nhjgdf]
_WORKFLOW_DIRS = [
    "transport_request_workflow",
    "rental_settlement_workflow",
    "driver_clearance_workflow",
    "salis_payment_request_workflow",
    "fuel_request_workflow",
    "fuel_claim_workflow",
    "fuel_exception_case_workflow",
    "dispatch_trip_workflow",
    # [#bxfoca]
    "movement_cost_recovery_workflow",
    "movement_cost_transfer_workflow",
    "vehicle_damage_write_off_workflow",
]

# [#ijqd52]
_STATE_STYLE = {
    # [#80vakv]
    "New": "Primary",
    "Validated": "Primary",
    "Approved": "Primary",
    "Scheduled": "Warning",
    "Fulfilled": "Success",
    "Rejected": "Danger",
    "Cancelled": "Danger",
    # [#rtbkfv]
    "Draft": "Primary",
    "Reconciled": "Warning",
    "Disputed": "Danger",
    "Paid": "Success",
    # [#4i7fog]
    "Open": "Warning",
    "In Progress": "Primary",
    "Cleared": "Success",
    "Blocked": "Danger",
    # [#r2yz72]
    "Pending Finance": "Warning",
    "Approved by Finance": "Primary",
    # [#poky3p]
    "Waiting": "Warning",
    "Resolved": "Primary",
    "Closed": "Success",
    # [#9nszle]
    "Completed": "Success",
    # [#bbzd6n]
    "Done": "Success",
    "Failed": "Danger",
    "Reverted": "Warning",
    # [#mrgswh]
    "Submitted to Movement": "Warning",
    # [#8wu4sl]
    "Under Investigation": "Primary",
    "Evidence Required": "Warning",
    # [#c13yy3]
    "Planned": "Primary",
    "Dispatched": "Warning",
}


def _load_definition(dir_name):
    """Load a shipped Workflow JSON definition from salis/workflow/<dir>/.

    The canonical definitions remain in the Salis module folder
    ``salis/workflow/<dir>/<dir>.json`` (the design artifact / single source of
    truth); this seeder lives under ``apex_core/setup/seeders/`` after the setup
    consolidation, so the path is resolved against the app root rather than the
    seeder's own location.
    """
    path = os.path.join(
        frappe.get_app_path("apex", "salis", "workflow"),
        dir_name,
        dir_name + ".json",
    )
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def seed_salis_workflows():
    """Create the Salis native Workflows if absent. Idempotent + existence-guarded
    on the target DocType and every referenced state/action master — safe to
    re-run (install + every migrate)."""
    for dir_name in _WORKFLOW_DIRS:
        # [#3iky5e]
        sp = "wf_seed"
        frappe.db.savepoint(sp)
        try:
            definition = _load_definition(dir_name)
            seed_one(definition, _STATE_STYLE)
        except Exception:
            # [#5rxgad]
            frappe.log_error(
                title=f"seed_salis_workflows failed: {dir_name}",
                message=frappe.get_traceback(),
            )
            frappe.db.rollback(save_point=sp)
    frappe.db.commit()
