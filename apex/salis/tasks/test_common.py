# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Salis fleet-queue shared helpers' own decisions.

``assign_role`` and ``reconcile_role_queue`` are the framework-facing machinery
(tested at apex_core.utils.role_assignment); what belongs to THIS module is the
severity->priority default and the reconcile-only-publishes-when-something-
cleared branch, so both are exercised directly with the machinery mocked out.
"""

from __future__ import annotations

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from apex.salis.tasks.common import _queue_document, _reconcile_queue, _vehicle_project


class TestQueueDocumentSeverityMapping(FrappeTestCase):
    def test_critical_severity_maps_to_high_priority(self):
        with patch("apex.salis.tasks.common.assign_role") as assign_role, patch(
            "apex.salis.tasks.common._publish_operations_alert"
        ), patch("apex.salis.tasks.common.frappe.db.savepoint"), patch(
            "apex.salis.tasks.common.frappe.get_doc"
        ):
            _queue_document("Salis Vehicle", "SV-000001", "Critical", "msg")
        self.assertEqual(assign_role.call_args.kwargs["priority"], "High")

    def test_unknown_severity_falls_back_to_medium(self):
        with patch("apex.salis.tasks.common.assign_role") as assign_role, patch(
            "apex.salis.tasks.common._publish_operations_alert"
        ), patch("apex.salis.tasks.common.frappe.db.savepoint"), patch(
            "apex.salis.tasks.common.frappe.get_doc"
        ):
            _queue_document("Salis Vehicle", "SV-000001", "Unrecognised", "msg")
        self.assertEqual(assign_role.call_args.kwargs["priority"], "Medium")


class TestReconcileQueuePublishesOnlyWhenSomethingCleared(FrappeTestCase):
    def test_publishes_when_something_was_cleared(self):
        with patch(
            "apex.salis.tasks.common.reconcile_role_queue", return_value=2
        ), patch("apex.salis.tasks.common._publish_operations_alert") as publish:
            cleared = _reconcile_queue("Vehicle Suspension", [])
        self.assertEqual(cleared, 2)
        publish.assert_called_once_with(None)

    def test_does_not_publish_when_nothing_cleared(self):
        with patch(
            "apex.salis.tasks.common.reconcile_role_queue", return_value=0
        ), patch("apex.salis.tasks.common._publish_operations_alert") as publish:
            cleared = _reconcile_queue("Vehicle Suspension", [])
        self.assertEqual(cleared, 0)
        publish.assert_not_called()


class TestVehicleProjectNeverRaises(FrappeTestCase):
    def test_blank_vehicle_returns_none_without_a_lookup(self):
        with patch("apex.salis.tasks.common.frappe.db.get_value") as get_value:
            self.assertIsNone(_vehicle_project(None))
        get_value.assert_not_called()

    def test_a_lookup_failure_is_swallowed_to_none(self):
        with patch(
            "apex.salis.tasks.common.frappe.db.get_value", side_effect=Exception("db down")
        ), patch("apex.salis.tasks.common.frappe.log_error") as log_error:
            self.assertIsNone(_vehicle_project("SV-000001"))
        log_error.assert_called_once()
