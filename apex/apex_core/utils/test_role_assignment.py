# Copyright (c) 2026, afmcoltd
"""``assign_role`` must not hand a scoped document to a holder outside its scope.

The consequence is not a merely useless ToDo. ``assign_to.add`` answers an assignee who
cannot read the document by SHARING it with them (frappe/desk/form/assign_to.py:98-110),
so a site-wide fan-out over a building- or project-scoped DocType grants the read the row
scope denied. These cases pin the narrowing to the framework's own permission check.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from apex.apex_core.utils import role_assignment


class TestAssignRoleScope(unittest.TestCase):
    HOLDERS = ("scoped@example.com", "outside@example.com")

    def _assign(self, permitted):
        with patch.object(role_assignment, "role_holders", return_value=list(self.HOLDERS)), patch.object(
            role_assignment, "frappe"
        ) as frappe_mock, patch(
            "frappe.desk.form.assign_to.add"
        ) as add:
            frappe_mock.has_permission.side_effect = lambda doc=None, user=None: user in permitted
            count = role_assignment.assign_role("Building", "B-1", "Safety Officer", "check")
        return count, add

    def test_a_holder_denied_the_document_is_not_assigned(self):
        count, add = self._assign({"scoped@example.com"})

        self.assertEqual(count, 1)
        self.assertEqual(add.call_args.args[0]["assign_to"], ["scoped@example.com"])

    def test_the_permission_check_reads_the_document_itself(self):
        """A doctype-only check would pass every holder — the scope lives on the row."""
        with patch.object(role_assignment, "role_holders", return_value=["a@example.com"]), patch.object(
            role_assignment, "frappe"
        ) as frappe_mock, patch("frappe.desk.form.assign_to.add"):
            frappe_mock.has_permission.return_value = True

            role_assignment.assign_role("Building", "B-1", "Safety Officer", "check")

        frappe_mock.get_doc.assert_called_once_with("Building", "B-1")
        self.assertIs(
            frappe_mock.has_permission.call_args.kwargs["doc"],
            frappe_mock.get_doc.return_value,
        )

    def test_nobody_permitted_assigns_nobody(self):
        count, add = self._assign(set())

        self.assertEqual(count, 0)
        add.assert_not_called()
