# Copyright (c) 2026, afmcoltd


from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import operations_alerts

FAKE_REF = frappe._dict(reference_type="Salis Vehicle", reference_name="V-TEST-0001")


class TestUnassignAlertDoesNotSwallowARealFailure(FrappeTestCase):
    def test_a_permission_error_from_assign_to_remove_propagates(self):
        with patch.object(
            operations_alerts, "_queue_ref_checked", return_value=FAKE_REF
        ), patch.object(
            operations_alerts.assign_to,
            "remove",
            side_effect=frappe.PermissionError("no write on this document"),
        ):
            with self.assertRaises(frappe.PermissionError):
                operations_alerts.unassign_alert("Q-TEST-0001")

    def test_the_ordinary_not_assigned_case_still_returns_ok(self):
        with patch.object(
            operations_alerts, "_queue_ref_checked", return_value=FAKE_REF
        ), patch.object(operations_alerts.assign_to, "remove") as mock_remove, patch.object(
            frappe, "get_all", return_value=[]
        ):
            result = operations_alerts.unassign_alert("Q-TEST-0001")

        mock_remove.assert_called_once_with("Salis Vehicle", "V-TEST-0001", frappe.session.user)
        self.assertEqual(result, {"ok": True, "name": "Q-TEST-0001", "assignees": []})
