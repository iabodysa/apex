# Copyright (c) 2026, AFMCO and contributors
"""A-085 Findings 2 & 4 - new reversal / rework transitions on the Salis native
Workflows.

Asserted against the ACTIVE Workflow records. The definitions arrive as fixtures,
imported on install and on every migrate, so a transition present on the live
Workflow proves both the shipped edit and that the import carried it:

  * Vehicle Damage Write-Off: Approved -> Cancel -> Cancelled (Fleet Manager +
    System Manager), so an approved write-off can be reversed natively to the
    docstatus-2 Cancelled state instead of being stuck;
  * Movement Cost Transfer:  Rejected -> Revise -> Draft (rework);
  * Salis Payment Request:   Rejected -> Revise -> Draft (rework);
  * Transport Request:       Rejected -> Reopen -> New  (rework).
"""

import frappe
from frappe.model.workflow import get_workflow_name
from frappe.tests.utils import FrappeTestCase


def _transitions(workflow_name):
    wf = frappe.get_doc("Workflow", workflow_name)
    return {(t.state, t.action, t.next_state, t.allowed) for t in wf.transitions}


class TestSalisWorkflowReversalTransitions(FrappeTestCase):
    def _require_active(self, doctype, workflow_name):
        if get_workflow_name(doctype) != workflow_name:
            raise AssertionError(
                f"{workflow_name!r} not active for {doctype!r} "
                "(salis_workflow_seed regression)"
            )

    def test_vdwo_approved_cancel_transition(self):
        self._require_active("Vehicle Damage Write-Off", "Vehicle Damage Write-Off Workflow")
        trans = _transitions("Vehicle Damage Write-Off Workflow")
        self.assertIn(("Approved", "Cancel", "Cancelled", "Fleet Manager"), trans)
        self.assertIn(("Approved", "Cancel", "Cancelled", "System Manager"), trans)

    def test_vdwo_cancelled_is_a_cancel_state(self):
        self._require_active("Vehicle Damage Write-Off", "Vehicle Damage Write-Off Workflow")
        wf = frappe.get_doc("Workflow", "Vehicle Damage Write-Off Workflow")
        cancelled = next((s for s in wf.states if s.state == "Cancelled"), None)
        self.assertIsNotNone(cancelled, "Cancelled state must exist")
        self.assertEqual(str(cancelled.doc_status), "2")

    def test_movement_cost_transfer_rejected_revise(self):
        self._require_active("Movement Cost Transfer", "Movement Cost Transfer Workflow")
        trans = _transitions("Movement Cost Transfer Workflow")
        for role in ("Fleet Project Manager", "Fleet Manager", "System Manager"):
            self.assertIn(("Rejected", "Revise", "Draft", role), trans)

    def test_salis_payment_request_rejected_revise(self):
        self._require_active("Salis Payment Request", "Salis Payment Request Workflow")
        trans = _transitions("Salis Payment Request Workflow")
        for role in ("Fleet Supervisor", "Fleet Project Manager", "Fleet Manager"):
            self.assertIn(("Rejected", "Revise", "Draft", role), trans)

    def test_transport_request_rejected_reopen(self):
        self._require_active("Transport Request", "Transport Request Workflow")
        trans = _transitions("Transport Request Workflow")
        for role in ("Fleet Supervisor", "Fleet Manager"):
            self.assertIn(("Rejected", "Reopen", "New", role), trans)
