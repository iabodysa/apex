"""State-machine tests: a document may only be created in its initial status
(closing the insert-bypass), and illegal status jumps are rejected."""

import unittest

import frappe


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
        with self.assertRaises(frappe.ValidationError):
            self._new(status="Closed").insert(ignore_permissions=True)

    def test_new_inserts_then_legal_and_illegal_transitions(self):
        t = self._new(status="New").insert(ignore_permissions=True)
        t.status = "In Progress"          # legal
        t.save(ignore_permissions=True)
        t.status = "Closed"               # illegal: must pass through Resolved
        with self.assertRaises(frappe.ValidationError):
            t.save(ignore_permissions=True)
        frappe.delete_doc("Support Ticket", t.name, ignore_permissions=True, force=True)
        frappe.db.commit()


class TestDispatchTripStateFlow(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_insert_at_completed_blocked(self):
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": "Dispatch Trip", "status": "Completed"}).insert(
                ignore_permissions=True)
