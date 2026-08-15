from unittest import TestCase
from unittest.mock import patch

import frappe

from apex.apex_core.utils.portal_identity import DRIVER
from apex.salis.api import driver_portal, masar_routes
from apex.salis.api.driver_portal import execution, personal, trips


class TestMasarDriverExecution(TestCase):
    @patch.object(trips, "_attach_boarding_counts")
    @patch.object(trips, "_attach_trip_log_state")
    @patch.object(trips, "_label_trips")
    @patch.object(trips, "_resolve_driver", return_value="DRV-1")
    @patch.object(trips, "_require_enabled")
    @patch.object(trips.frappe, "get_all", return_value=[])
    def test_today_lists_only_assigned_dispatched_trips(
        self, get_all, _enabled, _driver, _labels, _logs, _boarding
    ):
        trips.my_trips_today()

        filters = get_all.call_args.kwargs["filters"]
        self.assertEqual(filters["driver"], "DRV-1")
        self.assertEqual(filters["status"], "Dispatched")

    @patch("apex.salis.api.boarding_flow._manifest_request_names", return_value=["TR-1", "TR-2"])
    @patch("apex.salis.api.masar._registered_workers")
    @patch("apex.salis.api.masar._ordered_trip_stops", return_value=[])
    @patch.object(trips, "_trip_route_maps_url", return_value=None)
    @patch.object(trips, "_attach_stop_progress")
    @patch.object(trips, "_enrich_workers_with_phone")
    @patch.object(trips.frappe.db, "exists", return_value=False)
    @patch.object(trips.frappe.db, "get_value")
    @patch.object(trips, "_resolve_driver", return_value="DRV-1")
    @patch.object(trips, "_require_enabled")
    def test_trip_route_includes_workers_from_assigned_requests(
        self,
        _enabled,
        _driver,
        get_value,
        _exists,
        _phones,
        _progress,
        _maps,
        _stops,
        registered_workers,
        manifest_requests,
    ):
        get_value.side_effect = [
            frappe._dict(
                name="DT-1",
                trip_title="رحلة المستشفى",
                route_plan="RP-1",
                route_template="RT-1",
                vehicle="BUS-1",
                transport_request="TR-1",
                depart_time=None,
                return_time=None,
                status="Dispatched",
            ),
            "ABC 123",
        ]
        registered_workers.side_effect = [
            [
                {"employee": "EMP-1", "employee_name": "عامل 1"},
                {"employee": "EMP-2", "employee_name": "عامل 2"},
            ],
            [
                {"employee": "EMP-2", "employee_name": "عامل 2"},
                {"employee": "EMP-3", "employee_name": "عامل 3"},
            ],
        ]

        payload = trips.my_trip_route("DT-1")

        manifest_requests.assert_called_once_with("DT-1", "TR-1")
        self.assertEqual(
            [worker["employee"] for worker in payload["workers"]],
            ["EMP-1", "EMP-2", "EMP-3"],
        )
        self.assertEqual(payload["expected_count"], 3)
        _stops.assert_called_once_with("DT-1", "RP-1")
        self.assertEqual(payload["route_name"], "رحلة المستشفى")

    @patch.object(masar_routes.frappe, "get_all")
    def test_actual_trip_stops_override_legacy_route_plan(self, get_all):
        get_all.return_value = [
            frappe._dict(
                name="ROW-1",
                idx=1,
                stop_name="المستشفى",
                stop_key="hospital",
                location="https://maps.example/hospital",
                planned_time=None,
                passengers=2,
                accommodation_building=None,
                latitude=24.7,
                longitude=46.7,
            )
        ]

        stops = masar_routes._ordered_trip_stops("DT-1", "RP-OLD")

        self.assertEqual(stops[0]["route_stop"], "ROW-1")
        self.assertEqual(stops[0]["stop_key"], "hospital")
        self.assertEqual(get_all.call_count, 1)
        self.assertEqual(
            get_all.call_args.kwargs["filters"],
            {"parent": "DT-1", "parenttype": "Dispatch Trip"},
        )

    @patch.object(masar_routes.frappe, "get_all")
    def test_legacy_route_stops_are_fallback_only(self, get_all):
        get_all.side_effect = [
            [],
            [
                frappe._dict(
                    name="ROW-OLD",
                    idx=1,
                    stop_name="السكن",
                    stop_key=None,
                    location=None,
                    planned_time=None,
                    passengers=3,
                    accommodation_building=None,
                    latitude=None,
                    longitude=None,
                )
            ],
        ]

        stops = masar_routes._ordered_trip_stops("DT-OLD", "RP-OLD")

        self.assertEqual(stops[0]["route_stop"], "ROW-OLD")
        self.assertEqual(get_all.call_args.kwargs["filters"]["parenttype"], "Route Plan")

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

    @patch("apex.salis.api.boarding_flow._manifest_employees", return_value=[])
    @patch("apex.salis.api.boarding_flow.ensure_trip_boarding_state")
    @patch.object(execution, "_trip_log_state", return_value={"started": True})
    @patch.object(execution.frappe, "get_doc")
    @patch.object(execution.frappe.db, "get_value", return_value=None)
    @patch.object(execution, "_resolve_my_trip", return_value={"vehicle": "BUS-1"})
    @patch.object(execution, "_resolve_driver", return_value="DRV-1")
    @patch.object(execution, "_require_enabled")
    def test_start_seeds_the_existing_boarding_state(
        self, _enabled, _driver, _trip, _value, get_doc, _state, ensure_state, _manifest
    ):
        get_doc.return_value.insert.return_value = None

        execution.start_my_trip("DT-1")

        ensure_state.assert_called_once_with("DT-1")

    @patch("apex.salis.api.boarding_flow._publish")
    @patch("apex.salis.api.boarding_flow._manifest_employees", return_value=["EMP-1", "EMP-2"])
    @patch("apex.salis.api.boarding_flow.ensure_trip_boarding_state")
    @patch.object(execution, "_trip_log_state", return_value={"started": True})
    @patch.object(execution.frappe, "get_doc")
    @patch.object(execution.frappe.db, "get_value", return_value=None)
    @patch.object(execution, "_resolve_my_trip", return_value={"vehicle": "BUS-1"})
    @patch.object(execution, "_resolve_driver", return_value="DRV-1")
    @patch.object(execution, "_require_enabled")
    def test_start_notifies_each_worker_portal_room(
        self,
        _enabled,
        _driver,
        _trip,
        _value,
        get_doc,
        _state,
        _ensure,
        manifest,
        publish,
    ):
        get_doc.return_value.insert.return_value = None

        execution.start_my_trip("DT-1")

        manifest.assert_called_once_with("DT-1")
        publish.assert_called_once_with(
            "driver_trip_update",
            "DT-1",
            {"status": "Started"},
            driver="DRV-1",
            employees=["EMP-1", "EMP-2"],
        )

    @patch("apex.apex_core.utils.portal_identity.portal_room", return_value="driver:opaque")
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
