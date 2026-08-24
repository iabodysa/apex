# Copyright (c) 2026, afmcoltd


from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils import role_assignment
from apex.apex_core.utils.role_assignment import role_holders_escalating


class TestRoleHoldersEscalating(FrappeTestCase):

    def setUp(self):
        self._real = role_assignment.role_holders

    def tearDown(self):
        role_assignment.role_holders = self._real

    def _holders(self, mapping):
        role_assignment.role_holders = lambda role: mapping.get(role, [])

    def test_the_first_occupied_rung_wins_alone(self):
        self._holders({"HR Manager": ["hr@example.com"], "System Manager": ["sm@example.com"]})
        self.assertEqual(
            role_holders_escalating("HR Manager", "System Manager"), ["hr@example.com"]
        )

    def test_an_empty_first_rung_falls_through(self):
        self._holders({"System Manager": ["sm@example.com"]})
        self.assertEqual(
            role_holders_escalating("HR Manager", "System Manager"), ["sm@example.com"]
        )

    def test_no_occupied_rung_returns_empty_not_none(self):
        self._holders({})
        self.assertEqual(role_holders_escalating("HR Manager", "System Manager"), [])

    def test_order_decides_which_rung_answers(self):
        self._holders({"HR Manager": ["hr@example.com"], "System Manager": ["sm@example.com"]})
        self.assertEqual(
            role_holders_escalating("System Manager", "HR Manager"), ["sm@example.com"]
        )

    def test_guest_is_dropped_by_the_rung_it_would_occupy(self):
        self.assertEqual(self._real.__module__, "apex.apex_core.utils.role_assignment")
        role_assignment.role_holders = self._real
        self.assertNotIn("Guest", role_holders_escalating("Guest"))


class TestClearAssignmentLetsTheNativeCheckRun(FrappeTestCase):

    def test_close_all_assignments_is_called_with_no_ignore_permissions(self):
        with patch.object(role_assignment, "close_all_assignments") as mock_close:
            with patch.object(frappe, "get_all", return_value=["TODO-0001"]):
                role_assignment.clear_assignment("DocType", "some-doc")
        mock_close.assert_called_once_with("DocType", "some-doc")

    def test_a_document_reader_has_no_todo_left_open_against_them(self):
        todo = frappe.get_doc(
            {
                "doctype": "ToDo",
                "allocated_to": "Administrator",
                "reference_type": "DocType",
                "reference_name": "ToDo",
                "description": "apex test: clear_assignment permission gate",
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        try:
            with self.set_user("Guest"):
                with self.assertRaises(frappe.PermissionError):
                    role_assignment.clear_assignment("DocType", "ToDo")
        finally:
            frappe.delete_doc("ToDo", todo.name, ignore_permissions=True, force=True)
