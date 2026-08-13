from unittest import TestCase
from unittest.mock import patch

import frappe

from apex.salis.api import masar


class TestMasarWorkerHome(TestCase):
    @patch.object(masar, "_resolve_worker", return_value="EMP-1")
    @patch.object(masar, "get_worker_context", return_value={"employee": {"name": "EMP-1"}, "documents": []})
    @patch.object(masar, "get_worker_transport", return_value={"upcoming": [], "history": []})
    @patch.object(masar, "get_worker_accommodation", return_value={"assignment": {"name": "HA-1"}, "bed": None})
    @patch.object(masar, "get_worker_custody", return_value={"items": []})
    @patch.object(masar, "list_worker_requests", return_value=[])
    def test_home_is_one_bounded_worker_read_model(
        self, requests, custody, accommodation, transport, profile, _worker
    ):
        result = masar.get_worker_home()

        self.assertEqual(result["profile"], profile.return_value)
        self.assertEqual(result["accommodation"], accommodation.return_value)
        self.assertEqual(result["custody"], custody.return_value)
        self.assertEqual(result["transport"], transport.return_value)
        self.assertEqual(result["requests"], requests.return_value)

    @patch.object(masar.boarding_window, "resolve", return_value={"state": "waiting"})
    @patch.object(masar, "_ordered_trip_stops", return_value=[])
    @patch.object(masar, "_ordered_stops")
    def test_worker_transport_reads_actual_trip_stops(
        self, legacy_stops, trip_stops, _boarding_window
    ):
        request = frappe._dict(
            name="TR-1",
            dispatch_trip="DT-1",
            route_plan="RP-OLD",
            pickup_datetime=None,
            status="Scheduled",
        )
        lookups = {
            "live": {},
            "status": {"DT-1": "Dispatched"},
            "depart": {"DT-1": None},
            "rated": set(),
            "vehicle": {},
            "driver": {},
        }

        payload = masar._transport_trip(request, lookups, None, frappe.utils.now_datetime())

        trip_stops.assert_called_once_with("DT-1", "RP-OLD")
        legacy_stops.assert_not_called()
        self.assertEqual(payload["dispatch_trip"], "DT-1")
