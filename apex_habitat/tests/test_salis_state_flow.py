"""State-machine tests: a document may only be created in its initial status
(closing the insert-bypass), and illegal status jumps are rejected.

The Support Ticket state-flow tests were removed when the custom Support Ticket
DocType was retired in favour of the native ERPNext Issue (Issue carries no
initial-status guard and no custom workflow). Dispatch Trip still proves the
controller-level initial-status guard."""

import unittest

import frappe


class TestDispatchTripStateFlow(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_insert_at_completed_blocked(self):
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": "Dispatch Trip", "status": "Completed"}).insert(
                ignore_permissions=True)
