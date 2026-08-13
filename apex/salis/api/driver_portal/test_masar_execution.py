from unittest import TestCase
from unittest.mock import patch

import frappe

from apex.apex_core.utils.portal_token_security import DRIVER
from apex.salis.api import driver_portal
from apex.salis.api.driver_portal import execution, personal, trips


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

    @patch("apex.salis.api.boarding_flow.ensure_trip_boarding_state")
    @patch.object(execution, "_trip_log_state", return_value={"started": True})
    @patch.object(execution.frappe, "get_doc")
    @patch.object(execution.frappe.db, "get_value", return_value=None)
    @patch.object(execution, "_resolve_my_trip", return_value={"vehicle": "BUS-1"})
    @patch.object(execution, "_resolve_driver", return_value="DRV-1")
    @patch.object(execution, "_require_enabled")
    def test_start_seeds_the_existing_boarding_state(
        self, _enabled, _driver, _trip, _value, get_doc, _state, ensure_state
    ):
        get_doc.return_value.insert.return_value = None

        execution.start_my_trip("DT-1")

        ensure_state.assert_called_once_with("DT-1")

    @patch("apex.apex_core.utils.portal_token_security.portal_room", return_value="driver:opaque")
    @patch.object(personal, "_resolve_linked_employee", return_value="EMP-1")
    @patch.object(personal, "_resolve_driver", return_value="DRV-1")
    @patch.object(personal, "_require_enabled")
    @patch("apex.salis.api.driver_portal.trips.my_trips_today", return_value=[])
    def test_today_returns_the_driver_realtime_room(
        self, _trips, _enabled, _driver, _employee, portal_room
    ):
        payload = personal.get_masar_today()

        self.assertEqual(payload["realtime_room"], "driver:opaque")
        portal_room.assert_called_once_with(DRIVER)
