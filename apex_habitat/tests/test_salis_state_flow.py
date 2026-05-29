"""State-machine tests: a document may only be created in its initial status
(closing the insert-bypass), and illegal status jumps are rejected.

Support Ticket transitions are now owned by the native Support Ticket Workflow
(see test_support_ticket_workflow), so the only controller-level state guard
remaining is the initial-status guard (a ticket must be created as New). The
illegal-jump enforcement is proven on the workflow: a non-offered action is
rejected by ``apply_workflow``."""

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name


class TestSupportTicketStateFlow(unittest.TestCase):
    def _new(self, status=None):
        data = {"doctype": "Support Ticket", "raised_by": "Administrator",
                "category": "Vehicle", "subject": "state-flow test"}
        if status:
            data["status"] = status
        return frappe.get_doc(data)

    def setUp(self):
        frappe.set_user("Administrator")

    def test_insert_at_terminal_status_blocked(self):
        # The initial-status guard stays in the controller (the workflow does not
        # cover a direct insert at a later/terminal status).
        with self.assertRaises(frappe.ValidationError):
            self._new(status="Closed").insert(ignore_permissions=True)

    def test_illegal_jump_rejected_by_workflow(self):
        # New -> Closed skips Resolved: that action is not offered from New, so
        # the workflow rejects it. (Administrator drives the workflow here.)
        if get_workflow_name("Support Ticket") != "Support Ticket Workflow":
            self.skipTest("Support Ticket Workflow not seeded on this site")
        t = self._new(status="New").insert(ignore_permissions=True)
        offered = {tr.action for tr in get_transitions(t)}
        self.assertNotIn("Close", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(t, "Close")
        frappe.delete_doc("Support Ticket", t.name, ignore_permissions=True, force=True)
        frappe.db.commit()


class TestDispatchTripStateFlow(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_insert_at_completed_blocked(self):
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": "Dispatch Trip", "status": "Completed"}).insert(
                ignore_permissions=True)
