from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.doctype.dispatch_trip.dispatch_trip import (
    DispatchTrip,
    _normalise_request_assignments,
    _request_rider_count,
    assign_requests_to_trip,
    create_ad_hoc_trip,
)


class TestDispatchTripAggregate(FrappeTestCase):
    def _trip(self, **values):
        data = {
            "doctype": "Dispatch Trip",
            "trip_date": "2026-08-14",
            "status": "Planned",
            "vehicle": "VEH-1",
            "driver": "DRV-1",
        }
        data.update(values)
        return DispatchTrip(data)

    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.db.get_value")
    def test_direct_assignment_resolves_trip_context_without_route_plan(
        self, get_value
    ):
        get_value.return_value = frappe._dict(
            route_template="RT-1",
            project="PROJ-1",
            driver="DRV-1",
            vehicle="VEH-1",
            shift_name="Morning",
            assignment_name="Housing · Morning · Project",
        )
        trip = self._trip(route_assignment="RA-1")

        trip._resolve_route_context()

        self.assertEqual(trip.route_template, "RT-1")
        self.assertEqual(trip.project, "PROJ-1")
        self.assertEqual(trip.trip_title, "Housing · Morning · Project · 2026-08-14")
        self.assertFalse(trip.route_plan)

    def test_direct_trip_is_dispatch_ready_without_route_plan(self):
        trip = self._trip(
            route_template="RT-1",
            project="PROJ-1",
            stops=[
                {"stop_key": "pickup", "stop_name": "Housing"},
                {"stop_key": "dropoff", "stop_name": "Project"},
            ],
            assigned_requests=[
                {
                    "transport_request": "TR-1",
                    "pickup_stop": "pickup",
                    "dropoff_stop": "dropoff",
                }
            ],
        )

        trip._enforce_dispatch_readiness()

    def test_ad_hoc_trip_is_dispatch_ready_with_its_own_stops(self):
        trip = self._trip(
            trip_type="Ad Hoc",
            project="PROJ-1",
            stops=[
                {"stop_key": "hospital", "stop_name": "Hospital"},
                {"stop_key": "office", "stop_name": "Office"},
            ],
            assigned_requests=[
                {
                    "transport_request": "TR-1",
                    "pickup_stop": "hospital",
                    "dropoff_stop": "office",
                }
            ],
        )

        trip._enforce_dispatch_readiness()

    def test_request_mapping_must_reference_trip_stops(self):
        trip = self._trip(
            stops=[{"stop_key": "pickup", "stop_name": "Housing"}],
            assigned_requests=[
                {
                    "transport_request": "TR-1",
                    "pickup_stop": "pickup",
                    "dropoff_stop": "missing",
                }
            ],
        )

        with self.assertRaises(frappe.ValidationError):
            trip._validate_request_stop_mappings()

    def test_request_names_are_the_union_of_legacy_and_assigned_rows(self):
        trip = self._trip(
            transport_request="TR-1",
            assigned_requests=[
                {"transport_request": "TR-1"},
                {"transport_request": "TR-2"},
            ],
        )

        self.assertEqual(trip._request_names(), ["TR-1", "TR-2"])

    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.drive_transport_request")
    def test_completion_fulfils_every_request_in_one_transaction(self, drive):
        trip = self._trip(
            name="DT-1",
            transport_request="TR-1",
            assigned_requests=[{"transport_request": "TR-2"}],
        )

        trip._fulfil_transport_requests()

        self.assertEqual(
            drive.call_args_list,
            [
                call(
                    "TR-1",
                    action="Confirm Fulfilment",
                    target_state="Fulfilled",
                    extra_fields={
                        "fulfilled_on": drive.call_args_list[0].kwargs["extra_fields"][
                            "fulfilled_on"
                        ],
                        "assigned_vehicle": "VEH-1",
                        "assigned_driver": "DRV-1",
                        "dispatch_trip": "DT-1",
                    },
                ),
                call(
                    "TR-2",
                    action="Confirm Fulfilment",
                    target_state="Fulfilled",
                    extra_fields={
                        "fulfilled_on": drive.call_args_list[1].kwargs["extra_fields"][
                            "fulfilled_on"
                        ],
                        "assigned_vehicle": "VEH-1",
                        "assigned_driver": "DRV-1",
                        "dispatch_trip": "DT-1",
                    },
                ),
            ],
        )

    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.revert_transport_request")
    def test_cancellation_reverses_every_request(self, revert):
        trip = self._trip(
            transport_request="TR-1",
            assigned_requests=[{"transport_request": "TR-2"}],
        )

        trip._revert_transport_requests()

        self.assertEqual(
            [item.args[0] for item in revert.call_args_list],
            ["TR-1", "TR-2"],
        )

    def test_request_assignment_requires_explicit_mapping_on_multi_stop_trip(self):
        trip = self._trip(
            stops=[
                {"stop_key": "housing", "stop_name": "Housing"},
                {"stop_key": "office", "stop_name": "Office"},
                {"stop_key": "hospital", "stop_name": "Hospital"},
            ]
        )

        with self.assertRaises(frappe.ValidationError):
            _normalise_request_assignments(["TR-1"], trip)

    def test_request_rider_count_includes_registered_and_ad_hoc_passengers(self):
        request = frappe._dict(
            worker_count=1,
            passenger_count=0,
            workers=[frappe._dict(employee="EMP-1")],
            adhoc_passengers=[
                frappe._dict(full_name="Guest 1"),
                frappe._dict(full_name="Guest 2"),
            ],
        )

        self.assertEqual(_request_rider_count(request), 3)

    def test_request_rider_count_uses_declared_count_without_a_manifest(self):
        request = frappe._dict(
            worker_count=0,
            passenger_count=4,
            workers=[],
            adhoc_passengers=[],
        )

        self.assertEqual(_request_rider_count(request), 4)

    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.get_all")
    def test_passengers_include_employee_and_guest_with_request_stops(self, get_all):
        def records(doctype, **kwargs):
            if doctype == "Transport Request Worker":
                return [frappe._dict(parent="TR-1", employee="EMP-1", idx=1)]
            if doctype == "Employee":
                return [frappe._dict(name="EMP-1", employee_name="Ahmad")]
            if doctype == "Transport Request Ad Hoc Passenger":
                return [
                    frappe._dict(
                        parent="TR-1", full_name="Khalid", id_number="ID-1", idx=1
                    )
                ]
            return []

        get_all.side_effect = records
        trip = self._trip(
            stops=[
                {"stop_key": "housing", "stop_name": "Housing"},
                {"stop_key": "hospital", "stop_name": "Hospital"},
            ],
            assigned_requests=[
                {
                    "transport_request": "TR-1",
                    "pickup_stop": "housing",
                    "dropoff_stop": "hospital",
                }
            ],
        )

        trip._sync_passengers()

        self.assertEqual(
            [
                (
                    row.passenger_type,
                    row.passenger_name,
                    row.pickup_stop,
                    row.dropoff_stop,
                )
                for row in trip.boarding_state
            ],
            [
                ("Employee", "Ahmad", "housing", "hospital"),
                ("Guest", "Khalid", "housing", "hospital"),
            ],
        )

    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.drive_transport_request")
    @patch(
        "apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.has_permission",
        return_value=True,
    )
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.get_roles")
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.get_doc")
    def test_assignment_preflights_every_request_before_mutating_trip(
        self, get_doc, get_roles, _has_permission, drive
    ):
        get_roles.return_value = ["Fleet Supervisor"]
        trip = self._trip(
            name="DT-1",
            stops=[
                {"stop_key": "housing", "stop_name": "Housing"},
                {"stop_key": "project", "stop_name": "Project"},
            ],
        )
        first = frappe._dict(
            name="TR-1",
            status="Approved",
            assigned_to_trip=None,
            dispatch_trip=None,
            worker_count=1,
            transport_purpose="Shift Relocation",
        )
        second = frappe._dict(
            name="TR-2",
            status="Cancelled",
            assigned_to_trip=None,
            dispatch_trip=None,
            worker_count=1,
            transport_purpose="Other",
        )
        get_doc.side_effect = [trip, first, second]

        with self.assertRaises(frappe.ValidationError):
            assign_requests_to_trip(
                "DT-1",
                [
                    {
                        "transport_request": "TR-1",
                        "pickup_stop": "housing",
                        "dropoff_stop": "project",
                    },
                    {
                        "transport_request": "TR-2",
                        "pickup_stop": "housing",
                        "dropoff_stop": "project",
                    },
                ],
            )

        self.assertFalse(trip.assigned_requests)
        drive.assert_not_called()

    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.drive_transport_request")
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.has_permission")
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.get_roles")
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.get_doc")
    def test_assignment_requires_write_permission_on_each_request(
        self, get_doc, get_roles, has_permission, drive
    ):
        get_roles.return_value = ["Fleet Supervisor"]
        has_permission.side_effect = [True, False]
        trip = self._trip(
            name="DT-1",
            stops=[
                {"stop_key": "housing", "stop_name": "Housing"},
                {"stop_key": "project", "stop_name": "Project"},
            ],
        )
        trip.save = MagicMock()
        request = frappe._dict(
            name="TR-1",
            status="Approved",
            assigned_to_trip=None,
            dispatch_trip=None,
            worker_count=1,
            transport_purpose="Shift Relocation",
        )
        get_doc.side_effect = [trip, request]

        with self.assertRaises(frappe.PermissionError):
            assign_requests_to_trip(
                "DT-1",
                {
                    "transport_request": "TR-1",
                    "pickup_stop": "housing",
                    "dropoff_stop": "project",
                },
            )

        self.assertFalse(trip.assigned_requests)
        drive.assert_not_called()

    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.assign_requests_to_trip")
    @patch(
        "apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.has_permission",
        return_value=True,
    )
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.get_roles")
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.get_doc")
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.db.release_savepoint")
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.db.savepoint")
    def test_ad_hoc_creation_inserts_trip_then_reuses_atomic_assignment(
        self, savepoint, _release, get_doc, get_roles, _has_permission, assign
    ):
        get_roles.return_value = ["Fleet Supervisor"]
        trip = SimpleNamespace(name="DT-1", insert=MagicMock())
        get_doc.return_value = trip
        assign.return_value = ["TR-1"]

        result = create_ad_hoc_trip(
            {
                "project": "PROJ-1",
                "trip_date": "2026-08-14",
                "vehicle": "VEH-1",
                "driver": "DRV-1",
                "stops": [
                    {"stop_key": "housing", "stop_name": "Housing"},
                    {"stop_key": "office", "stop_name": "Office"},
                ],
                "status": "Completed",
                "assigned_requests": [{"transport_request": "TR-OTHER"}],
            },
            [
                {
                    "transport_request": "TR-1",
                    "pickup_stop": "housing",
                    "dropoff_stop": "office",
                }
            ],
        )

        savepoint.assert_called_once_with("create_ad_hoc_dispatch_trip")
        payload = get_doc.call_args.args[0]
        self.assertEqual(payload["doctype"], "Dispatch Trip")
        self.assertEqual(payload["trip_type"], "Ad Hoc")
        self.assertEqual(payload["status"], "Planned")
        self.assertNotIn("assigned_requests", payload)
        trip.insert.assert_called_once_with()
        assign.assert_called_once()
        self.assertEqual(assign.call_args.args[0], "DT-1")
        self.assertEqual(result, {"name": "DT-1", "assigned_requests": ["TR-1"]})

    @patch(
        "apex.salis.doctype.dispatch_trip.dispatch_trip.assign_requests_to_trip",
        side_effect=frappe.ValidationError("assignment failed"),
    )
    @patch(
        "apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.has_permission",
        return_value=True,
    )
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.get_roles")
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.get_doc")
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.db.rollback")
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.db.savepoint")
    def test_ad_hoc_creation_rolls_back_trip_when_assignment_fails(
        self, savepoint, rollback, get_doc, get_roles, _has_permission, _assign
    ):
        get_roles.return_value = ["Fleet Supervisor"]
        trip = SimpleNamespace(name="DT-1", insert=MagicMock())
        get_doc.return_value = trip

        with self.assertRaises(frappe.ValidationError):
            create_ad_hoc_trip(
                {
                    "project": "PROJ-1",
                    "trip_date": "2026-08-14",
                    "vehicle": "VEH-1",
                    "driver": "DRV-1",
                    "stops": [
                        {"stop_key": "housing", "stop_name": "Housing"},
                        {"stop_key": "office", "stop_name": "Office"},
                    ],
                },
                [{"transport_request": "TR-1"}],
            )

        rollback.assert_called_once_with(save_point="create_ad_hoc_dispatch_trip")
