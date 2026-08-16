# Copyright (c) 2026, AFMCO and contributors
"""a rejected cost recovery must be resolvable from the desk.

`Rejected` on the Movement Cost Recovery Workflow carries `doc_status` 1, so rejecting a
recovery SUBMITS it. Every transition out of the workflow leaves from some other state, so
the document arrives somewhere immutable with no action offered and no desk Cancel button
(`workflow_guard._enforce` allows a bare cancel only when the user holds an authorised
transition to a `doc_status` 2 state, and from Rejected there was none). Only console
access could move it again.

The proof is a sequence, not a diff: a Fleet Manager creates a recovery, rejects it, and
must then reach a terminal state through an action the desk would actually offer —
`get_transitions` is exactly what the desk reads to draw those buttons.

`test_rejected_offered_nothing_before_the_fix` is the other half the card asks for: it
pins the states that were dead ends, so the day someone reintroduces one this fails.
"""

import frappe
from frappe.model.workflow import apply_workflow, get_transitions
from frappe.tests.utils import FrappeTestCase

WORKFLOW = "Movement Cost Recovery Workflow"
MANAGER_ROLE = "Fleet Manager"


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestARejectedRecoveryCanStillBeResolved(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.manager = frappe.get_doc(
            {
                "doctype": "User",
                "email": f"mcr-{_h()}@example.com".lower(),
                "first_name": "Fleet Manager Fixture",
                "send_welcome_email": 0,
                "roles": [{"role": MANAGER_ROLE}],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "User", cls.manager.name, force=True, ignore_permissions=True
        )
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _rejected_recovery(self):
        doc = frappe.get_doc(
            {
                "doctype": "Movement Cost Recovery",
                "recovery_type": "Other",
                "amount": 25,
                "basis_evidence": "/files/mcr-fixture.pdf",
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(self._drop, doc.name)
        frappe.set_user(self.manager.name)
        apply_workflow(doc, "Reject")
        self.assertEqual(doc.status, "Rejected")
        self.assertEqual(doc.docstatus, 1, "rejecting is expected to submit the record")
        return doc

    def _drop(self, name):
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "Movement Cost Recovery", name, "docstatus", 0, update_modified=False
        )
        frappe.delete_doc(
            "Movement Cost Recovery", name, force=True, ignore_permissions=True
        )

    def test_the_rejecting_manager_is_offered_a_way_out(self):
        """The desk draws its workflow buttons from get_transitions, so an empty list is
        a document with no action on screen."""
        doc = self._rejected_recovery()
        actions = [t.action for t in get_transitions(doc)]
        self.assertTrue(
            actions,
            "a rejected recovery offered the manager who rejected it no action at all",
        )

    def test_the_way_out_reaches_a_terminal_state(self):
        """An offered button is only an answer if pressing it resolves the document."""
        doc = self._rejected_recovery()
        apply_workflow(doc, "Cancel")
        doc.reload()
        self.assertEqual(doc.status, "Cancelled")
        self.assertEqual(doc.docstatus, 2)

    def test_no_state_in_this_workflow_strands_a_submitted_document(self):
        """The sweep the card asks for, held as a test so it cannot regress. A submitted
        state with no outgoing transition is legitimate when it is an END — the recovery
        was collected, waived, or voided. A refusal is not an end, and Rejected was the
        only refusal state in the app that had no way out."""
        workflow = frappe.get_doc("Workflow", WORKFLOW)
        leaves = {t.state for t in workflow.transitions}
        stranded = sorted(
            s.state
            for s in workflow.states
            if str(s.doc_status) == "1" and s.state not in leaves
        )
        self.assertEqual(
            stranded,
            ["Recovered", "Waived"],
            "the submitted states with no way out must be the two that mean the recovery is over",
        )
