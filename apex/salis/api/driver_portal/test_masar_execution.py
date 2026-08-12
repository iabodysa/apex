from unittest import TestCase
from unittest.mock import patch

import frappe

from apex.salis.api import driver_portal
from apex.salis.api.driver_portal import trips


class TestMasarDriverExecution(TestCase):
    @patch.object(trips, "_attach_boarding_counts")
    @patch.object(trips, "_attach_trip_log_state")
    @patch.object(trips, "_label_trips")
    @patch.object(trips, "_attach_trip_maps")
    @patch.object(trips, "_resolve_driver", return_value="DRV-1")
    @patch.object(trips, "_require_enabled")
    @patch.object(trips.frappe, "get_all", return_value=[])
    def test_today_lists_only_assigned_dispatched_trips(
        self, get_all, _enabled, _driver, _maps, _labels, _logs, _boarding
    ):
        trips.my_trips_today()

        filters = get_all.call_args.kwargs["filters"]
        self.assertEqual(filters["driver"], "DRV-1")
        self.assertEqual(filters["status"], "Dispatched")

    @patch.object(driver_portal.frappe.db, "get_value")
    def test_execution_rejects_a_trip_not_dispatched(self, get_value):
        get_value.return_value = frappe._dict(
            name="DT-1",
            driver="DRV-1",
            status="Planned",
            trip_date=frappe.utils.today(),
        )

        with self.assertRaises(frappe.ValidationError):
            driver_portal._resolve_my_trip("DT-1", "DRV-1")
