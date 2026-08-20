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
from apex.salis.api import boarding_flow
from frappe.utils import today
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name
from apex.tests._helpers import _user
from apex.tests.factories import make_project, make_vehicle, purge_doc, purge_trip_request

# No case in this module inserts a Dispatch Trip: every trip here is an in-memory
# DispatchTrip/doc object exercising one controller method directly (aggregate
# logic under mocks, or a single validate-time guard), so the module needs none
# of the usual link-fixture auto-dependencies.


def _times_trip(status, depart, ret):
    """An unsaved Dispatch Trip carrying only what ``_validate_trip_times`` reads."""
    return frappe.get_doc(
        {
            "doctype": "Dispatch Trip",
            "status": status,
            "depart_time": depart,
            "return_time": ret,
        }
    )


class TestDispatchTripAggregate(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

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

    def test_request_rider_count_covers_manifest_and_declared_fallback(self):
        """_request_rider_count sums the manifest when riders are listed, and
        falls back to the declared count when none are."""
        with_manifest = frappe._dict(
            worker_count=1,
            passenger_count=0,
            workers=[frappe._dict(employee="EMP-1")],
            adhoc_passengers=[
                frappe._dict(full_name="Guest 1"),
                frappe._dict(full_name="Guest 2"),
            ],
        )
        self.assertEqual(
            _request_rider_count(with_manifest),
            3,
            "a manifest counts every registered worker and ad-hoc passenger",
        )

        without_manifest = frappe._dict(
            worker_count=0,
            passenger_count=4,
            workers=[],
            adhoc_passengers=[],
        )
        self.assertEqual(
            _request_rider_count(without_manifest),
            4,
            "with no manifest rows, the declared passenger_count is the total",
        )

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

    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.db.savepoint")
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.get_doc")
    @patch("apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.get_roles")
    @patch(
        "apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.has_permission",
        return_value=True,
    )
    @patch(
        "apex.salis.doctype.dispatch_trip.dispatch_trip.frappe.throw",
        side_effect=frappe.ValidationError,
    )
    @patch(
        "apex.salis.doctype.dispatch_trip.dispatch_trip._", side_effect=lambda value: value
    )
    def test_ad_hoc_creation_rejects_serialized_empty_request_list_before_insert(
        self,
        _translate,
        _throw,
        _has_permission,
        get_roles,
        get_doc,
        savepoint,
    ):
        get_roles.return_value = ["Fleet Supervisor"]

        with self.assertRaises(frappe.ValidationError):
            create_ad_hoc_trip(
                {
                    "project": "PROJ-1",
                    "trip_date": "2026-08-14",
                    "vehicle": "VEH-1",
                    "driver": "DRV-1",
                    "stops": [{"stop_key": "housing", "stop_name": "Housing"}],
                },
                "[]",
            )

        get_doc.assert_not_called()
        savepoint.assert_not_called()
    # Frappe stores an empty Int field as 0, so an odometer_end set while
    # odometer_start is left at its 0 default would pass a naive `if not start`
    # check and silently break distance/odometer-advance accounting on submit.
    # _validate_odometer requires both-or-neither and end >= start.

    def _odometer_trip(self, start, end):
        doc = frappe.new_doc("Dispatch Trip")
        doc.odometer_start = start
        doc.odometer_end = end
        return doc

    def test_odometer_end_set_while_start_zero_throws(self):
        doc = self._odometer_trip(0, 150)
        with self.assertRaises(frappe.ValidationError):
            doc._validate_odometer()

    def test_odometer_start_set_while_end_zero_throws(self):
        doc = self._odometer_trip(100, 0)
        with self.assertRaises(frappe.ValidationError):
            doc._validate_odometer()

    def test_odometer_end_less_than_start_throws(self):
        doc = self._odometer_trip(200, 150)
        with self.assertRaises(frappe.ValidationError):
            doc._validate_odometer()

    def test_odometer_both_unset_passes(self):
        doc = self._odometer_trip(0, 0)
        doc._validate_odometer()

    def test_odometer_valid_pair_passes(self):
        doc = self._odometer_trip(100, 250)
        doc._validate_odometer()
    # The guard only fires on a Completed trip with BOTH times set; a return
    # earlier than the depart is rejected, equal/later is accepted. Planned
    # trips are exempt (a freshly created trip carries an auto-filled nowtime
    # that would false-positive).

    def test_times_completed_return_before_depart_is_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            _times_trip("Completed", "10:00:00", "08:00:00")._validate_trip_times()

    def test_times_completed_return_after_depart_passes(self):
        _times_trip("Completed", "08:00:00", "10:00:00")._validate_trip_times()

    def test_times_completed_equal_times_pass(self):
        _times_trip("Completed", "09:00:00", "09:00:00")._validate_trip_times()

    def test_times_planned_reversed_times_are_exempt(self):
        _times_trip("Planned", "10:00:00", "08:00:00")._validate_trip_times()

    def test_times_completed_missing_one_time_is_exempt(self):
        _times_trip("Completed", "10:00:00", None)._validate_trip_times()

test_dependencies = ['Salis Vehicle', 'Salis Driver', 'Employee']
test_ignore = ['Salis Vehicle', 'Salis Driver', 'Route Plan', 'Transport Request', 'Payment Gateway', 'Employee', 'Company', 'Project', 'User', 'Role']


# --- merged from test_boarding_state_permlevel.py ---
RIDER = "rider-permlevel@apex.test"
class TestBoardingStatePermlevel(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("User", RIDER):
            user = frappe.get_doc({
                "doctype": "User",
                "email": RIDER,
                "first_name": "Rider",
                "send_welcome_email": 0,
                "roles": [{"role": "Driver"}],
            })
            user.insert(ignore_permissions=True)
        # Dispatch Trip is project-scoped by a has_permission hook, so the rider needs the scope
        # before permlevel is even reached. Without it the save fails on document access and the
        # field-level wall is never exercised.
        if not frappe.db.exists("Project", {"project_name": "Permlevel Scope"}):
            frappe.get_doc({"doctype": "Project", "project_name": "Permlevel Scope"}).insert(
                ignore_permissions=True
            )
        cls.project = frappe.db.get_value("Project", {"project_name": "Permlevel Scope"}, "name")
        if not frappe.db.exists("User Permission", {"user": RIDER, "for_value": cls.project}):
            frappe.get_doc({
                "doctype": "User Permission",
                "user": RIDER,
                "allow": "Project",
                "for_value": cls.project,
            }).insert(ignore_permissions=True)
        cls.trip = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "trip_type": "Ad Hoc",
            "trip_date": frappe.utils.today(),
            "status": "Planned",
            "project": cls.project,
        })
        cls.trip.insert(ignore_permissions=True)

    def setUp(self):
        frappe.set_user(RIDER)
        self.addCleanup(frappe.set_user, "Administrator")

    def test_the_flow_state_stays_writable(self):
        """boarding_state is left at permlevel 0, so the Driver role's ordinary write reaches it."""
        trip = frappe.get_doc("Dispatch Trip", self.trip.name)
        trip.append("boarding_state", {"status": "Pending", "notify_count": 0, "wait_count": 0})
        trip.save()
        self.assertEqual(len(frappe.get_doc("Dispatch Trip", self.trip.name).boarding_state), 1)

    def test_a_protected_field_is_reset_not_refused(self):
        """The vehicle sits at permlevel 1: the save succeeds and the value does not move."""
        trip = frappe.get_doc("Dispatch Trip", self.trip.name)
        before = trip.trip_title
        trip.trip_title = "rider rewrote this"
        trip.save()
        self.assertEqual(frappe.get_doc("Dispatch Trip", self.trip.name).trip_title, before)

    def test_the_wall_is_declared_where_it_belongs(self):
        """Every data field except the flow state carries the raised level."""
        meta = frappe.get_meta("Dispatch Trip")
        layout = {"Section Break", "Column Break", "Tab Break"}
        open_fields = [
            df.fieldname for df in meta.fields
            if df.fieldtype not in layout and not df.permlevel
        ]
        self.assertEqual(open_fields, ["boarding_state"])


# --- merged from test_dispatch_trip_assignment.py ---
def _h(n=12):
    return frappe.generate_hash(length=n).upper()
class TestDispatchTripAssignment(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._cleanup = []

        self.w1 = self._employee()
        self.w2 = self._employee()
        self.w3 = self._employee()

        self.req_a = self._request([self.w1, self.w2])
        self.req_b = self._request([self.w2, self.w3])

        self.vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "naming_series": "VEH-.######",
                "plate_number": "ASG " + _h(12),
                "status": "Active",
                "seat_capacity": 0,
            }
        )
        self.vehicle.flags.ignore_validate = True
        self.vehicle.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Salis Vehicle", self.vehicle.name))

        self.trip = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "naming_series": "DT-.######",
                "vehicle": self.vehicle.name,
                "trip_date": "2026-06-20",
                "status": "Planned",
                # A row's pickup/drop-off is derived from the trip's own stops, and
                # only while the trip carries at most two of them
                # (dispatch_trip._normalise_request_assignments); a stop-less trip is
                # refused before any request is read.
                "stops": [
                    {"stop_key": "pickup", "stop_name": "Housing Gate"},
                    {"stop_key": "dropoff", "stop_name": "Project Site"},
                ],
            }
        )
        self.trip.flags.ignore_validate = True
        self.trip.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Dispatch Trip", self.trip.name))

    def tearDown(self):
        frappe.set_user("Administrator")
        for dt, name in reversed(self._cleanup):
            frappe.delete_doc(dt, name, force=True, ignore_permissions=True)


    def _employee(self):
        emp = frappe.get_doc(
            {"doctype": "Employee", "first_name": "ASG-" + _h(), "naming_series": "HR-EMP-"}
        )
        emp.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Employee", emp.name))
        return emp.name

    def _request(self, workers):
        req = frappe.get_doc({"doctype": "Transport Request", "worker_count": len(workers)})
        for w in workers:
            req.append("workers", {"employee": w})
        req.flags.ignore_validate = True
        req.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        # Written after the insert because the bypassed validate is what would
        # otherwise derive worker_count. Scheduled is required: assign_requests_to_trip
        # refuses anything outside Approved/Scheduled, and Scheduled is the branch that
        # stamps the assignment fields directly instead of driving the request's own
        # workflow (which would need the request submitted).
        frappe.db.set_value(
            "Transport Request",
            req.name,
            {"worker_count": len(workers), "status": "Scheduled"},
            update_modified=False,
        )
        self._cleanup.append(("Transport Request", req.name))
        return req.name


    def test_assign_two_requests_unions_the_manifest(self):
        assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])

        union = set(boarding_flow._manifest_employees(self.trip.name))
        self.assertEqual(
            union,
            {self.w1, self.w2, self.w3},
            "the trip manifest is the de-duplicated union of both requests' workers",
        )

        self.trip.reload()
        seeded = {r.employee for r in self.trip.boarding_state}
        self.assertEqual(seeded, {self.w1, self.w2, self.w3})
        self.assertEqual(
            len(self.trip.boarding_state),
            3,
            "boarding state carries one row per union worker (w2 not doubled)",
        )

        # sync_passengers already rebuilt boarding_state during the assignment save,
        # so the trip-start top-up finds every union worker present and adds none.
        added = boarding_flow.ensure_trip_boarding_state(self.trip.name)
        self.assertEqual(added, 0)


    def test_assign_flags_each_request(self):
        assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])
        for req in (self.req_a, self.req_b):
            row = frappe.db.get_value(
                "Transport Request", req, ["is_assigned", "assigned_to_trip"], as_dict=True
            )
            self.assertTrue(row.is_assigned, f"{req} is flagged assigned")
            self.assertEqual(row.assigned_to_trip, self.trip.name)


    def test_capacity_guard_throws_on_exceed(self):
        frappe.db.set_value("Salis Vehicle", self.vehicle.name, "seat_capacity", 2)
        with self.assertRaises(frappe.ValidationError):
            assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])

    def test_capacity_guard_silent_when_capacity_unknown(self):
        result = assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])
        self.assertEqual(set(result), {self.req_a, self.req_b})

    def test_capacity_guard_allows_within_capacity(self):
        frappe.db.set_value("Salis Vehicle", self.vehicle.name, "seat_capacity", 5)
        result = assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])
        self.assertEqual(set(result), {self.req_a, self.req_b})


    def test_assign_is_idempotent(self):
        assign_requests_to_trip(self.trip.name, [self.req_a])
        result = assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])
        self.assertEqual(result.count(self.req_a), 1, "a re-assigned request is not duplicated")
        self.assertEqual(set(result), {self.req_a, self.req_b})


    def test_assign_unknown_request_throws_with_that_id(self):
        """A non-existent request id is rejected by name. Each row is loaded with
        frappe.get_doc, whose miss raises DoesNotExistError — a ValidationError
        subclass — carrying the id that could not be found."""
        missing = "TR-DOES-NOT-EXIST-" + _h()
        with self.assertRaises(frappe.ValidationError) as ctx:
            assign_requests_to_trip(self.trip.name, [self.req_a, missing])
        self.assertIn(missing, str(ctx.exception))


    def test_terminal_request_is_refused_by_name(self):
        """A Cancelled request is refused, named in the message: only Approved or
        Scheduled may be assigned. Every row is loaded and checked before the first
        one is appended, so the live request in the same selection is not flagged
        either — the selection is refused whole."""
        frappe.db.set_value("Transport Request", self.req_a, "status", "Cancelled")
        with self.assertRaises(frappe.ValidationError) as ctx:
            assign_requests_to_trip(self.trip.name, [self.req_a, self.req_b])
        self.assertIn(self.req_a, str(ctx.exception))
        for req in (self.req_a, self.req_b):
            self.assertFalse(
                frappe.db.get_value("Transport Request", req, "is_assigned"),
                f"{req} stays unflagged when the selection is refused",
            )


# --- merged from test_dispatch_trip_releases_requests.py ---
class TestATripReleasesItsRequests(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.project = self._project()
        self.request = self._request()
        self.trip = self._trip()

    def _new(self, doctype, **values):
        doc = frappe.get_doc({"doctype": doctype, **values}).insert(
            ignore_permissions=True, ignore_mandatory=True
        )
        self.addCleanup(self._drop, doctype, doc.name)
        return doc

    @staticmethod
    def _drop(doctype, name):
        if not frappe.db.exists(doctype, name):
            return
        doc = frappe.get_doc(doctype, name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

    def _project(self):
        """Borrowed, never built: ERPNext's Project fixture is not idempotent."""
        existing = frappe.db.get_value("Project", {}, "name")
        if existing:
            return existing
        return self._new(
            "Project", project_name="_DT Project " + frappe.generate_hash(length=12).upper()
        ).name

    def _request(self):
        doc = self._new(
            "Transport Request",
            service_line="Administrative Trip",
            request_type="Administrative Trip / Document Signing",
            destination="_DT Release Destination",
            project=self.project,
            status="New",
        )
        # Placed in the state the workflow would have put it in; the helper under test
        # only accepts an Approved or Scheduled request.
        frappe.db.set_value(
            "Transport Request", doc.name, {"status": "Approved", "docstatus": 1}
        )
        return doc.name

    def _trip(self):
        """Two stops of its own, because the assignment helper derives the pickup and
        drop-off from the trip's own stop keys when the caller names neither."""
        trip = self._new(
            "Dispatch Trip",
            trip_date=today(),
            status="Planned",
            project=self.project,
            stops=[
                {"stop_key": "stop-1", "stop_name": "_DT Pickup"},
                {"stop_key": "stop-2", "stop_name": "_DT Dropoff"},
            ],
        ).name
        assign_requests_to_trip(trip, [{"transport_request": self.request}])
        return trip

    def _claim(self):
        return frappe.db.get_value(
            "Transport Request", self.request, ["is_assigned", "assigned_to_trip"], as_dict=True
        )

    def test_assignment_is_what_puts_the_claim_on(self):
        """Positive control: without this the release assertions could pass on a request
        that was never claimed in the first place."""
        claim = self._claim()
        self.assertEqual(claim.is_assigned, 1)
        self.assertEqual(claim.assigned_to_trip, self.trip)

    def test_deleting_the_draft_trip_releases_the_request(self):
        """A draft never reaches cancel. It is deleted, and the claim has to go with it."""
        frappe.delete_doc("Dispatch Trip", self.trip, force=True, ignore_permissions=True)

        claim = self._claim()
        self.assertEqual(claim.is_assigned, 0, "the request is still claimed by a deleted trip")
        self.assertIsNone(claim.assigned_to_trip)

    def test_the_cancel_reversal_releases_the_request(self):
        """The other door. ``on_cancel`` delegates the whole reversal to this method, and
        it is called directly rather than by driving the trip to Completed and back:
        submitting a Dispatch Trip writes a Trip Fulfilment Ledger, whose naming series
        makes the round trip contend for ``tabseries`` and fail intermittently. What is
        being graded is the reversal, not the workflow that reaches it.

        ``is_assigned`` must come back as an explicit 0, not NULL — NULL is not 0 to the
        filter the re-assignment guard reads.
        """
        frappe.db.set_value(
            "Transport Request",
            self.request,
            {"status": "Fulfilled", "dispatch_trip": self.trip},
        )

        frappe.get_doc("Dispatch Trip", self.trip)._revert_transport_requests()

        claim = self._claim()
        self.assertEqual(claim.is_assigned, 0)
        self.assertIsNone(claim.assigned_to_trip)
        self.assertEqual(
            frappe.db.get_value("Transport Request", self.request, "status"), "Scheduled"
        )

    def test_on_cancel_is_what_runs_that_reversal(self):
        """Guard of the guard: the case above would keep passing if ``on_cancel`` stopped
        calling it, and every cancelled trip would leave its requests locked again."""
        import ast
        import inspect
        import textwrap

        from apex.salis.doctype.dispatch_trip.dispatch_trip import DispatchTrip

        tree = ast.parse(textwrap.dedent(inspect.getsource(DispatchTrip.on_cancel)))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertIn("_revert_transport_requests", called)

    def test_a_released_request_can_be_claimed_by_another_trip(self):
        """The outcome the two cases above exist for, asserted end to end."""
        frappe.delete_doc("Dispatch Trip", self.trip, force=True, ignore_permissions=True)
        successor = self._new(
            "Dispatch Trip",
            trip_date=today(),
            status="Planned",
            project=self.project,
            stops=[
                {"stop_key": "stop-1", "stop_name": "_DT Pickup"},
                {"stop_key": "stop-2", "stop_name": "_DT Dropoff"},
            ],
        ).name

        assign_requests_to_trip(successor, [{"transport_request": self.request}])

        self.assertEqual(self._claim().assigned_to_trip, successor)


# --- merged from test_dispatch_trip_workflow.py ---
WORKFLOW = "Dispatch Trip Workflow"
def _h_dispatch_trip_workflow(n=12):
    """Short random hash suffix for unique fixture names."""
    return frappe.generate_hash(length=n).upper()
def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}
class TestDispatchTripWorkflow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # mandatory Salis workflow (salis_workflow_seed, every install/migrate);
        # absence is a regression - FAIL, never skip.
        if get_workflow_name("Dispatch Trip") != WORKFLOW:
            raise AssertionError(
                f"Mandatory Salis workflow {WORKFLOW!r} not active for "
                "'Dispatch Trip' (salis_workflow_seed regression)"
            )
        frappe.set_user("Administrator")
        cls.supervisor = _user("dtwf_sup@example.com", "Fleet Supervisor")
        cls.pmanager = _user("dtwf_pm@example.com", "Fleet Project Manager")
        cls.manager = _user("dtwf_mgr@example.com", "Fleet Manager")
        cls.project = make_project("DT Workflow Project")
        for u in (cls.supervisor, cls.pmanager):
            if not frappe.db.exists(
                "User Permission",
                {"user": u, "allow": "Project", "for_value": cls.project},
            ):
                frappe.get_doc({
                    "doctype": "User Permission",
                    "user": u,
                    "allow": "Project",
                    "for_value": cls.project,
                }).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for u in (cls.supervisor, cls.pmanager):
            frappe.db.delete("User Permission",
                             {"user": u, "allow": "Project", "for_value": cls.project})
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")


    @staticmethod
    def _driver(name):
        d = frappe.db.get_value("Salis Driver", {"full_name": name}, "name")
        if not d:
            d = frappe.get_doc({
                "doctype": "Salis Driver", "full_name": name, "status": "Active",
            }).insert(ignore_permissions=True).name
        return d

    @staticmethod
    def _make_vehicle(suffix=None, odometer=0):
        plate = "SSF-" + (suffix or _h_dispatch_trip_workflow(12))
        existing = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
        if existing:
            return existing
        return frappe.get_doc({
            "doctype": "Salis Vehicle",
            "plate_number": plate,
            "status": "Active",
            "odometer": odometer,
        }).insert(ignore_permissions=True).name

    @staticmethod
    def _make_driver(suffix=None):
        full_name = "SSF Driver " + (suffix or _h_dispatch_trip_workflow(12))
        existing = frappe.db.get_value("Salis Driver", {"full_name": full_name}, "name")
        if existing:
            return existing
        return frappe.get_doc({
            "doctype": "Salis Driver",
            "full_name": full_name,
            "status": "Active",
        }).insert(ignore_permissions=True).name

    def _scheduled_tr(self):
        """A Transport Request driven (as Administrator) all the way to Scheduled
        with a submitted Route Plan, ready for a Dispatch Trip. Returns
        ``(tr_doc, route_plan_name)``.

        The plan carries its two stops because a Dispatch Trip copies its executable
        route from the plan (``trip_manifest.copy_route_stops``) and dispatch
        readiness refuses a trip with no stop to run."""
        tr = frappe.get_doc({
            "doctype": "Transport Request",
            "service_line": "Administrative Trip",
            "request_type": "Administrative Trip / Document Signing",
            "destination": "Ministry Office",
            "from_location": "HQ",
            "to_location": "Ministry Office",
            "project": self.project,
            "requested_by": self.pmanager,
            "source_channel": "Desk",
            "status": "New",
        }).insert(ignore_permissions=True)
        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()
        frappe.set_user(self.manager)
        apply_workflow(tr, "Authorize (Operations)")
        frappe.set_user("Administrator")
        tr.reload()
        rp = frappe.get_doc({
            "doctype": "Route Plan",
            "route_name": "DT WF Route",
            "transport_request": tr.name,
            "project": self.project,
            "stops": [
                {"stop_name": "HQ", "location": "HQ"},
                {"stop_name": "Ministry Office", "location": "Ministry Office"},
            ],
        }).insert(ignore_permissions=True)
        rp.submit()
        tr.reload()
        self.assertEqual(tr.status, "Scheduled")
        self.addCleanup(lambda: purge_trip_request(tr.name, rp.name))
        return tr, rp.name

    def _make_scheduled_tr(self, project):
        """A Transport Request driven all the way to Scheduled, with a submitted
        Route Plan. Returns ``(tr_doc, route_plan_name)``. The caller registers
        its own cleanup via ``addCleanup`` — unlike ``_scheduled_tr`` above, this
        variant does not clean up after itself.

        The plan carries its two stops because a Dispatch Trip copies its executable
        route from the plan (``trip_manifest.copy_route_stops``) and
        ``_enforce_dispatch_readiness`` refuses a trip with no stop to run."""
        tr = frappe.get_doc({
            "doctype": "Transport Request",
            "service_line": "Administrative Trip",
            "request_type": "Administrative Trip / Document Signing",
            "destination": "Ministry Office",
            "from_location": "HQ",
            "to_location": "Ministry Office",
            "project": project,
            "requested_by": self.pmanager,
            "source_channel": "Desk",
            "status": "New",
        }).insert(ignore_permissions=True)

        frappe.set_user(self.supervisor)
        apply_workflow(tr, "Validate")
        tr.reload()
        frappe.set_user(self.manager)
        apply_workflow(tr, "Authorize (Operations)")
        frappe.set_user("Administrator")
        tr.reload()

        rp = frappe.get_doc({
            "doctype": "Route Plan",
            "route_name": "SSF Route " + _h_dispatch_trip_workflow(12),
            "transport_request": tr.name,
            "project": project,
            "stops": [
                {"stop_name": "HQ", "location": "HQ"},
                {"stop_name": "Ministry Office", "location": "Ministry Office"},
            ],
        }).insert(ignore_permissions=True)
        rp.submit()
        tr.reload()
        self.assertEqual(tr.status, "Scheduled")
        return tr, rp.name

    def _new_trip(self, route_plan, vehicle, driver):
        dt = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "route_plan": route_plan,
            "vehicle": vehicle,
            "driver": driver,
            "trip_date": frappe.utils.today(),
            "status": "Planned",
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", dt.name))
        return dt

    def _make_trip(self, route_plan, vehicle, driver, status="Planned"):
        dt = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "route_plan": route_plan,
            "vehicle": vehicle,
            "driver": driver,
            "trip_date": frappe.utils.today(),
            "status": status,
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", dt.name))
        return dt


    # --- native workflow: seeding, lifecycle, cancel reversal, illegal jumps ----

    def test_workflow_is_seeded_and_active(self):
        self.assertEqual(get_workflow_name("Dispatch Trip"), WORKFLOW)
        self.assertTrue(frappe.db.get_value("Workflow", WORKFLOW, "is_active"))
        self.assertEqual(
            frappe.db.get_value("Workflow", WORKFLOW, "workflow_state_field"), "status"
        )
        states = {
            s.state: s.doc_status
            for s in frappe.get_doc("Workflow", WORKFLOW).states
        }
        self.assertEqual(states["Planned"], "0")
        self.assertEqual(states["Dispatched"], "0")
        self.assertEqual(states["Completed"], "1")
        self.assertEqual(states["Cancelled"], "2")


    def test_walk_to_completed_drives_tr_to_fulfilled_and_updates_odometer(self):
        tr, rp = self._scheduled_tr()
        vehicle = make_vehicle("DT-WF-1", odometer=100)
        driver = self._driver("DT WF Driver 1")
        dt = self._new_trip(rp, vehicle, driver)
        self.assertEqual(dt.docstatus, 0)

        frappe.set_user(self.supervisor)
        self.assertIn("Dispatch", _actions(dt))
        apply_workflow(dt, "Dispatch")
        dt.reload()
        self.assertEqual(dt.status, "Dispatched")
        self.assertEqual(dt.docstatus, 0)

        dt.completion_notes = "Delivered on time."
        dt.odometer_start = 100
        dt.odometer_end = 260
        dt.save(ignore_permissions=True)

        frappe.set_user(self.supervisor)
        self.assertIn(
            "Complete",
            _actions(dt),
            "the supervisor who dispatched the trip closes it; without this the "
            "finished trip stays on his active board and only a manager can clear it",
        )

        frappe.set_user(self.manager)
        self.assertIn("Complete", _actions(dt))
        apply_workflow(dt, "Complete")
        dt.reload()
        self.assertEqual(dt.status, "Completed")
        self.assertEqual(dt.docstatus, 1)

        tr.reload()
        self.assertEqual(tr.status, "Fulfilled")
        self.assertEqual(tr.dispatch_trip, dt.name)
        self.assertEqual(tr.assigned_vehicle, vehicle)
        self.assertEqual(tr.assigned_driver, driver)

        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", vehicle, "odometer"), 260
        )
        self.assertTrue(
            frappe.db.exists("Trip Fulfilment Ledger", {"dispatch_trip": dt.name})
        )


    def test_cancel_completed_trip_reverses_fulfilment(self):
        tr, rp = self._scheduled_tr()
        vehicle = make_vehicle("DT-WF-2", odometer=500)
        driver = self._driver("DT WF Driver 2")
        dt = self._new_trip(rp, vehicle, driver)

        frappe.set_user(self.manager)
        apply_workflow(dt, "Dispatch")
        dt.reload()
        dt.completion_notes = "Done."
        dt.odometer_start = 500
        dt.odometer_end = 540
        dt.save(ignore_permissions=True)
        apply_workflow(dt, "Complete")
        tr.reload()
        self.assertEqual(tr.status, "Fulfilled")
        self.assertTrue(
            frappe.db.exists("Trip Fulfilment Ledger", {"dispatch_trip": dt.name})
        )

        dt.reload()
        frappe.set_user(self.manager)
        self.assertIn("Cancel", _actions(dt))
        apply_workflow(dt, "Cancel")
        dt.reload()
        self.assertEqual(dt.status, "Cancelled")
        self.assertEqual(dt.docstatus, 2)

        tr.reload()
        self.assertEqual(tr.status, "Scheduled")
        self.assertIsNone(tr.dispatch_trip)
        self.assertIsNone(tr.assigned_vehicle)
        self.assertFalse(
            frappe.db.exists("Trip Fulfilment Ledger", {"dispatch_trip": dt.name})
        )


    def test_illegal_jump_planned_to_completed_blocked(self):
        tr, rp = self._scheduled_tr()
        vehicle = make_vehicle("DT-WF-3", odometer=0)
        driver = self._driver("DT WF Driver 3")
        dt = self._new_trip(rp, vehicle, driver)

        frappe.set_user(self.manager)
        offered = _actions(dt)
        self.assertIn("Dispatch", offered)
        self.assertNotIn("Complete", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(dt, "Complete")

    def test_draft_trip_is_never_offered_cancel(self):
        """A draft (Planned / Dispatched) trip is never offered Cancel — a
        draft -> Cancelled (docstatus 0 -> 2) transition is forbidden by Frappe,
        so it is intentionally absent. A draft trip is called off by deletion."""
        tr, rp = self._scheduled_tr()
        vehicle = make_vehicle("DT-WF-4", odometer=0)
        driver = self._driver("DT WF Driver 4")
        dt = self._new_trip(rp, vehicle, driver)

        frappe.set_user(self.manager)
        self.assertNotIn("Cancel", _actions(dt))
        apply_workflow(dt, "Dispatch")
        dt.reload()
        frappe.set_user(self.manager)
        self.assertNotIn("Cancel", _actions(dt))


    # --- controller-level state guards, independent of the workflow record -----

    def test_insert_at_non_planned_status_blocked(self):
        """Controller rejects a direct insert at any non-initial status — only
        the workflow may move a trip past Planned (Dispatched, Cancelled) or
        into a terminal state (Completed)."""
        for status in ("Completed", "Dispatched", "Cancelled"):
            with self.subTest(status=status):
                with self.assertRaises(frappe.ValidationError):
                    frappe.get_doc(
                        {"doctype": "Dispatch Trip", "status": status}
                    ).insert(ignore_permissions=True)

    def test_insert_at_planned_succeeds(self):
        """The only valid creation state is Planned; the insert must not raise."""
        dt = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "status": "Planned",
            "trip_date": frappe.utils.today(),
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", dt.name))
        self.assertEqual(dt.status, "Planned")
        self.assertEqual(dt.docstatus, 0)


    def test_happy_path_lifecycle(self):
        """A trip walks Planned → Dispatched → Completed via apply_workflow.

        Verifies status and docstatus at each step, and that completion_notes
        must be set before the Complete transition is applied. Side-effects
        (TR fulfilment, ledger) are proved above.
        """
        tr, rp = self._make_scheduled_tr(self.project)
        self.addCleanup(lambda: purge_trip_request(tr.name, rp))
        vehicle = self._make_vehicle("HP1")
        driver = self._make_driver("HP1")
        dt = self._make_trip(rp, vehicle, driver)

        self.assertEqual(dt.status, "Planned")
        self.assertEqual(dt.docstatus, 0)

        frappe.set_user(self.supervisor)
        self.assertIn("Dispatch", _actions(dt))
        apply_workflow(dt, "Dispatch")
        dt.reload()
        self.assertEqual(dt.status, "Dispatched")
        self.assertEqual(dt.docstatus, 0)

        frappe.set_user("Administrator")
        dt.completion_notes = "All workers delivered on time."
        dt.odometer_start = 1000
        dt.odometer_end = 1120
        dt.save(ignore_permissions=True)

        frappe.set_user(self.manager)
        self.assertIn("Complete", _actions(dt))
        apply_workflow(dt, "Complete")
        dt.reload()
        self.assertEqual(dt.status, "Completed")
        self.assertEqual(dt.docstatus, 1)


    def test_invalid_transition_from_planned_to_completed_blocked(self):
        """Workflow blocks the Complete action when the trip is still Planned.

        The transition table has no Planned → Completed edge, so apply_workflow
        must raise a ValidationError. This is a pure state-machine check, so a
        bare Planned trip is enough — no route, vehicle or driver is read by
        either the offered-actions lookup or the transition table.
        """
        dt = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "status": "Planned",
            "trip_date": frappe.utils.today(),
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", dt.name))

        frappe.set_user(self.manager)
        offered = _actions(dt)
        self.assertNotIn("Complete", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(dt, "Complete")


    def test_invalid_transition_from_completed_to_dispatched_blocked(self):
        """Once a trip is Completed (submitted), the only legal next action is
        Cancel (Fleet Manager → Cancelled/docstatus 2). Dispatch is not
        offered and apply_workflow must raise a ValidationError."""
        tr, rp = self._make_scheduled_tr(self.project)
        self.addCleanup(lambda: purge_trip_request(tr.name, rp))
        vehicle = self._make_vehicle("INV2")
        driver = self._make_driver("INV2")
        dt = self._make_trip(rp, vehicle, driver)

        frappe.set_user(self.manager)
        apply_workflow(dt, "Dispatch")
        dt.reload()
        dt.completion_notes = "Delivered."
        dt.odometer_start = 200
        dt.odometer_end = 240
        frappe.set_user("Administrator")
        dt.save(ignore_permissions=True)
        frappe.set_user(self.manager)
        apply_workflow(dt, "Complete")
        dt.reload()
        self.assertEqual(dt.status, "Completed")

        offered = _actions(dt)
        self.assertNotIn("Dispatch", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(dt, "Dispatch")


    def test_idempotent_transition_dispatch_twice_raises(self):
        """Applying the same Dispatch action twice must raise on the second call.

        After the first Dispatch the trip is in Dispatched state; the Dispatch
        action has no outgoing edge from Dispatched, so the second call must
        raise a ValidationError rather than silently succeeding or crashing.
        The trip never reaches docstatus 1 in this test, so a bare Planned
        trip (no route, vehicle or driver) carries the same state machine."""
        dt = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "status": "Planned",
            "trip_date": frappe.utils.today(),
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", dt.name))

        frappe.set_user(self.manager)
        apply_workflow(dt, "Dispatch")
        dt.reload()
        self.assertEqual(dt.status, "Dispatched")

        dt.reload()
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(dt, "Dispatch")


    def test_submit_without_vehicle_blocked(self):
        """before_submit enforces dispatch readiness: vehicle is required.

        A trip missing the vehicle field must not pass before_submit even when
        the workflow state is otherwise valid. We bypass the controller validate
        at insert time so the readiness check (before_submit) is the gate under
        test. completion_notes is set directly in the DB alongside the forced
        status so the earlier _require_completion_notes guard in validate()
        cannot fire first and mask the vehicle guard this test targets. The
        doc is submitted directly as Administrator so no role gate interferes;
        the message is asserted so a bare ValidationError from a different
        guard cannot pass as this one."""
        bare = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "status": "Planned",
            "trip_date": frappe.utils.today(),
        })
        bare.flags.ignore_validate = True
        bare.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", bare.name))

        bare.flags.ignore_validate = False
        bare.flags.ignore_mandatory = False

        frappe.db.set_value(
            "Dispatch Trip",
            bare.name,
            {"status": "Completed", "completion_notes": "Delivered."},
        )
        bare.reload()
        bare.flags.ignore_validate = False
        bare.flags.ignore_mandatory = False
        with self.assertRaises(frappe.ValidationError) as ctx:
            bare.submit()
        self.assertIn("Dispatch readiness", str(ctx.exception))
        self.assertIn("Vehicle", str(ctx.exception))


    def test_completion_notes_required_when_status_completed(self):
        """Saving a trip with status=Completed but no completion_notes raises.

        This guard lives in validate(), so it fires on every save, not only on
        submit. We bypass the workflow to set the status directly so we can
        exercise the controller guard in isolation."""
        bare = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "status": "Planned",
            "trip_date": frappe.utils.today(),
        })
        bare.flags.ignore_validate = True
        bare.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", bare.name))

        bare.status = "Completed"
        bare.completion_notes = ""
        with self.assertRaises(frappe.ValidationError):
            bare.save(ignore_permissions=True)


    def test_odometer_end_less_than_start_blocked(self):
        """Odometer end reading below start reading is rejected at validate.

        The doc is inserted clean (no bypass flags), so the guard runs on the
        first save as well. Values are then changed on the doc object (without
        a DB round-trip) and a second save must raise."""
        bare = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "status": "Planned",
            "trip_date": frappe.utils.today(),
            "odometer_start": 100,
            "odometer_end": 200,
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", bare.name))

        bare.odometer_start = 500
        bare.odometer_end = 300
        with self.assertRaises(frappe.ValidationError):
            bare.save(ignore_permissions=True)

    def test_lone_odometer_start_without_end_blocked(self):
        """Setting odometer_start without a matching odometer_end is rejected.

        _validate_odometer treats Int 0 as «not set» (both-or-neither rule).
        A positive start with end=0 has start_set=True, end_set=False and must
        raise a ValidationError."""
        bare = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "status": "Planned",
            "trip_date": frappe.utils.today(),
            "odometer_start": 100,
            "odometer_end": 200,
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Dispatch Trip", bare.name))

        bare.odometer_start = 100
        bare.odometer_end = 0
        with self.assertRaises(frappe.ValidationError):
            bare.save(ignore_permissions=True)


# --- merged from test_driver_user_fetch.py ---
DRIVER_NAME = "_Test Driver"
PLATE = "_T ABC 1001"
PORTAL_USER = "test@example.com"
class TestDriverUserFetch(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.user = PORTAL_USER
        self.driver = frappe.db.get_value("Salis Driver", {"full_name": DRIVER_NAME}, "name")
        self.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": PLATE}, "name")
        self.addCleanup(frappe.db.set_value, "Salis Driver", self.driver, "driver_user", None)
        frappe.db.set_value("Salis Driver", self.driver, "driver_user", self.user)

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_dispatch_trip_mirrors_driver_user(self):
        trip = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "trip_date": today(),
                "driver": self.driver,
                "status": "Planned",
            }
        )
        trip.insert(ignore_permissions=True)
        self.assertEqual(
            trip.driver_user,
            self.user,
            "Dispatch Trip.driver_user must fetch the linked driver's portal user.",
        )
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Dispatch Trip", trip.name, force=True, ignore_permissions=True
            )
        )

    def test_fuel_request_mirrors_driver_user(self):
        fr = frappe.get_doc(
            {
                "doctype": "Fuel Request",
                "request_type": "Standard",
                "vehicle": self.vehicle,
                "driver": self.driver,
                "request_date": today(),
                "requested_litres": 40,
                "status": "Pending",
            }
        )
        fr.insert(ignore_permissions=True)
        self.assertEqual(
            fr.driver_user,
            self.user,
            "Fuel Request.driver_user must fetch the linked driver's portal user.",
        )
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Fuel Request", fr.name, force=True, ignore_permissions=True
            )
        )

    def test_on_update_publishes_driver_trip_update(self):
        with patch("frappe.publish_realtime") as pub:
            trip = frappe.get_doc(
                {
                    "doctype": "Dispatch Trip",
                    "trip_date": today(),
                    "driver": self.driver,
                    "status": "Planned",
                }
            )
            trip.insert(ignore_permissions=True)
            self.addCleanup(
                lambda: frappe.delete_doc(
                    "Dispatch Trip", trip.name, force=True, ignore_permissions=True
                )
            )

        calls = [
            c
            for c in pub.call_args_list
            if c.args and c.args[0] == "driver_trip_update"
        ]
        self.assertTrue(
            calls,
            "on_update must publish a driver_trip_update so drivers' portals refetch.",
        )
        kwargs = calls[0].kwargs
        self.assertEqual(
            kwargs.get("doctype"),
            "Dispatch Trip",
            "driver_trip_update must be routed to the Dispatch Trip doctype room "
            "(the socket server gates delivery on read permission).",
        )
        self.assertTrue(
            kwargs.get("after_commit"),
            "driver_trip_update must be after_commit so subscribers read committed state.",
        )
        self.assertEqual(
            calls[0].args[1].get("name"),
            trip.name,
            "The advisory payload should carry the trip name.",
        )
