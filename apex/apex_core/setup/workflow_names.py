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

Each Workflow below is graded a DECISION or a RECORD. A Workflow is a decision only where a
transition REFUSES — ``Reject``, ``Dispute``, ``Block``, ``Return``, ``Revise`` or ``Reopen``;
``Cancel`` is abandonment and grades nothing. One with no refusing transition is a
Decisionless Workflow and encodes a sequence of facts, which a ``status`` Select with DocPerm
already expresses. The refusing transition is named so the grade can be re-checked against the
fixture rather than re-argued:

- Custody Damage Assessment — decision, ``Pending Approval -- Reject``.
- Dispatch Trip — RECORD. Its only acts are Dispatch, Complete and Cancel, and none refuses.
  It keeps its Workflow because ``Completed`` carries ``doc_status 1`` and
  ``apex/salis/utilisation_engine.py:61`` counts only a SUBMITTED Completed trip; a ``status``
  Select cannot set ``docstatus``, so replacing it would move a declared binding into Python.
- Driver Clearance — decision, ``Open|In Progress -- Block``. ``Clear`` carries the mechanical
  condition on returns and outstanding cases; ``Block`` is the supervisor's own refusal.
- Fuel Claim — decision, ``Submitted to Movement|Reconciled -- Dispute``. It refuses through
  Dispute, not Reject, and a scanner that watches for Reject alone grades it wrongly.
- Fuel Exception Case — decision, ``Open|Under Investigation|Evidence Required -- Reject``.
- Fuel Request — decision, ``Pending -- Reject``.
- Lease — decision, ``Pending Approval -- Reject`` held by Finance Manager.
- Movement Cost Recovery — decision, ``Open|Acknowledged -- Reject``.
- Movement Cost Transfer — decision, ``Pending Approval -- Reject``.
- Rental Settlement — decision, ``Reconciled -- Dispute``, the same Dispute-not-Reject shape.
- Route Assignment — decision, ``Pending -- Reject``.
- Salis Payment Request — decision, ``Pending Finance -- Reject``.
- Subcontractor Service Contract — decision, ``Pending Approval -- Reject``.
- Transport Request — decision, ``New|Validated -- Reject``.
- Utility Bill Entry — decision, ``Pending Approval -- Reject``.
- Vehicle Damage Write-Off — decision, ``Under Review -- Reject``.

No forward act may be restricted to a role that is absent when the act happens. Dispatch Trip
was the one breach: ``Fleet Supervisor`` could Dispatch a trip and watch it on the active board
(``apex/salis/api/route_supervisor.py:104`` filters ``status = Dispatched``) but only Fleet
Project Manager and Fleet Manager could Complete it, so a finished trip stayed on that board.
The role now holds the transition and the matching ``submit`` DocPerm, because ``Completed``
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
