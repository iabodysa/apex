# Copyright (c) 2026, afmcoltd
"""The Workflow records this app ships, named so the fixtures hook can select them.

Workflow is absent from ``frappe.model.sync.IMPORTABLE_DOCTYPES``, so a module folder
never imports one. ``frappe.utils.fixtures.import_fixtures`` does, on every migrate, and
that is the mechanism this app uses. The lists below are the fixture filters; they are
data, and they are derived from the shipped ``<module>/workflow/<name>/<name>.json``
design artifacts, which stay the source of truth for the definitions themselves.

States and actions are shared masters that a Workflow links to, so they must exist before
the definitions load. ``import_fixtures`` walks the fixtures directory with ``sorted()``,
and the filenames order them correctly.

A Workflow here earns its approval machinery only where a transition REFUSES — ``Reject``,
``Dispute``, ``Block``, ``Return``, ``Revise`` or ``Reopen``; ``Cancel`` is abandonment and
grades nothing. Fuel Claim and Rental Settlement refuse through ``Dispute`` rather than
``Reject``, so a scanner watching only for Reject grades both of them wrongly.
The invariant, written here rather than pointed at: a Workflow whose transitions carry no
refusing action is a **Decisionless Workflow** and earns no approval machinery, and the
grade is re-derived from WORKFLOWS below rather than trusted from a previous reading.

Dispatch Trip is that one, and it keeps its Workflow: ``Completed`` carries ``doc_status 1``
and ``apex/salis/utilisation_engine.py:61`` counts only a SUBMITTED Completed trip, so a plain
``status`` Select would move a declared binding into Python.

No forward act may be restricted to a role that is absent when the act happens: a role that can
Dispatch a trip can Complete it, and holds the matching ``submit`` DocPerm because ``Completed``
is ``doc_status 1``.
"""

WORKFLOWS = (
    "Custody Damage Assessment Workflow",
    "Dispatch Trip Workflow",
    "Driver Clearance Workflow",
    "Fuel Claim Workflow",
    "Fuel Exception Case Workflow",
    "Fuel Request Workflow",
    "Lease Workflow",
    "Maintenance Request Workflow",
    "Movement Cost Recovery Workflow",
    "Movement Cost Transfer Workflow",
    "Rental Settlement Workflow",
    "Route Assignment Workflow",
    "Salis Payment Request Workflow",
    "Subcontractor Service Contract Workflow",
    "Transport Request Workflow",
    "Utility Bill Entry Workflow",
    "Vehicle Damage Write-Off Workflow",
)

WORKFLOW_STATES = (
    "Acknowledged",
    "Active",
    "Approved",
    "Approved by Finance",
    "Blocked",
    "Cancelled",
    "Cleared",
    "Closed",
    "Completed",
    "Dispatched",
    "Disputed",
    "Done",
    "Draft",
    "Evidence Required",
    "Expired",
    "Failed",
    "Fulfilled",
    "In Progress",
    "New",
    "Open",
    "Paid",
    "Pending",
    "Pending Approval",
    "Pending Finance",
    "Planned",
    "Posted (memo)",
    "Reconciled",
    "Recovered",
    "Rejected",
    "Resolved",
    "Reverted",
    "Scheduled",
    "Submitted to Movement",
    "Terminated",
    "Under Investigation",
    "Under Review",
    "Validated",
    "Waived",
)

WORKFLOW_ACTIONS = (
    "Acknowledge",
    "Activate",
    "Approve",
    "Approve (Finance)",
    "Authorize (Operations)",
    "Authorize (Regional)",
    "Block",
    "Cancel",
    "Clear",
    "Close",
    "Complete",
    "Confirm Fulfilment",
    "Dispatch",
    "Dispute",
    "Mark Failed",
    "Mark Paid",
    "Post (memo)",
    "Re-reconcile",
    "Re-submit",
    "Reconcile",
    "Recover",
    "Reject",
    "Reopen",
    "Request Evidence",
    "Resolve",
    "Resume Investigation",
    "Revert",
    "Revise",
    "Schedule",
    "Start Investigation",
    "Start Processing",
    "Submit for Approval",
    "Submit for Review",
    "Submit to Finance",
    "Submit to Movement",
    "Terminate",
    "Validate",
    "Waive",
)
