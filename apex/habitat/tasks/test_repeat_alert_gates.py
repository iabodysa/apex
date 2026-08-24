# Copyright (c) 2026, afmcoltd


from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.tasks import maintenance, safety


class TestQueueOverdueRequestCommentsOnlyOnANewAssignment(FrappeTestCase):
    def test_no_comment_when_nobody_was_newly_assigned(self):
        with patch.object(maintenance, "assign_role", return_value=0), patch.object(
            frappe, "get_doc"
        ) as mock_get_doc:
            maintenance._queue_overdue_request(
                "MR-TEST-0001", "Medium", 10.0, 8, "Plumbing", "Open"
            )
            mock_get_doc.assert_not_called()

    def test_a_comment_is_written_on_a_new_assignment(self):
        with patch.object(maintenance, "assign_role", return_value=1), patch.object(
            frappe, "get_doc"
        ) as mock_get_doc:
            maintenance._queue_overdue_request(
                "MR-TEST-0001", "Medium", 10.0, 8, "Plumbing", "Open"
            )
            mock_get_doc.assert_called_once_with("Maintenance Request", "MR-TEST-0001")
            mock_get_doc.return_value.add_comment.assert_called_once()


class TestFlagBuildingsWithoutRoundsCommentsOnlyOnANewAssignment(FrappeTestCase):
    def _run(self, newly_assigned):
        fake_building = frappe._dict(
            name="B-TEST-0001", building_name="Test Building", responsible_supervisor=None
        )
        calls = iter([[fake_building], []])

        def fake_get_all(doctype, *a, **k):
            if doctype == "Building":
                return next(calls, [])
            return []

        with patch.object(
            safety.frappe, "get_all", side_effect=fake_get_all
        ), patch.object(safety.frappe.db, "exists", return_value=False), patch.object(
            safety, "assign_role", return_value=newly_assigned
        ), patch.object(safety, "_notify_role_system"), patch.object(
            safety, "_notify_operational"
        ) as mock_operational, patch.object(
            safety, "notify_user_system"
        ), patch.object(safety, "reconcile_role_queue"):
            safety._flag_buildings_without_rounds(frappe.logger())
        return mock_operational

    def test_no_comment_when_nobody_was_newly_assigned(self):
        self._run(newly_assigned=0).assert_not_called()

    def test_a_comment_is_written_on_a_new_assignment(self):
        self._run(newly_assigned=1).assert_called_once()
