from unittest import TestCase
from unittest.mock import patch

import frappe

from apex.salis.api.driver_portal import personal


class TestDriverPersonalService(TestCase):
    @patch.object(personal, "_resolve_driver", return_value="DRV-1")
    @patch.object(personal.frappe.db, "get_value", return_value="EMP-1")
    def test_linked_employee_is_server_resolved(self, get_value, _driver):
        self.assertEqual(personal._resolve_linked_employee(), "EMP-1")
        get_value.assert_called_once_with(
            "Salis Driver", {"name": "DRV-1", "status": "Active"}, "employee"
        )

    @patch.object(personal, "_resolve_driver", return_value="DRV-1")
    @patch.object(personal.frappe.db, "get_value", return_value=None)
    def test_missing_employee_fails_closed(self, _get_value, _driver):
        with self.assertRaises(frappe.PermissionError):
            personal._resolve_linked_employee(required=True)

    def test_personal_endpoints_accept_no_employee_argument(self):
        for endpoint in (
            personal.get_my_accommodation,
            personal.get_my_custody,
            personal.get_my_resident_requests,
        ):
            self.assertEqual(endpoint.__wrapped__.__code__.co_argcount, 0)

    @patch.object(personal, "_require_enabled")
    @patch.object(personal, "_resolve_driver", return_value="DRV-1")
    @patch.object(personal, "_resolve_linked_employee", return_value="EMP-1")
    @patch("apex.salis.api.driver_portal.trips.my_trips_today", return_value=[])
    def test_today_contains_masar_trip_and_personal_scope_only(
        self, my_trips, _employee, _driver, _enabled
    ):
        self.assertEqual(
            personal.get_masar_today(),
            {"driver": "DRV-1", "employee": "EMP-1", "trips": []},
        )
        my_trips.assert_called_once_with()
