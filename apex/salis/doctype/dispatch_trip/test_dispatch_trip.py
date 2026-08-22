# Copyright (c) 2026, afmcoltd
"""What a Dispatch Trip guarantees, asserted against the DocType itself.

A new trip must be created at status Planned (later states are reached only
through the Dispatch Trip Workflow); odometer start/end must be set together
and never run backwards; a trip marked Completed must carry completion notes;
and submission (the workflow's Complete transition) is refused until the trip
carries a vehicle, driver, trip date, project and at least one stop. Once a
trip legitimately reaches Completed with an odometer reading, the linked
vehicle's odometer advances to match.

Nothing rolls back between test methods in this class (``FrappeTestCase``
rolls back only once, at class teardown), so tests that mutate the shared
Salis Vehicle's odometer are ordered last and read it fresh rather than
assuming a starting value another test may have already changed.
"""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

test_dependencies = ["Salis Vehicle", "Salis Driver", "Project"]


class TestDispatchTrip(FrappeTestCase):
    def test_a_new_trip_created_directly_at_a_non_planned_status_is_refused(self):
        """Later states are reached only through the workflow, never a direct insert."""
        trip = frappe.copy_doc(frappe.get_test_records("Dispatch Trip")[0])
        trip.status = "Dispatched"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "must start as Planned",
            trip.insert,
        )

    def test_odometer_start_without_end_is_refused(self):
        """Half an odometer reading is not a reading; both ends or neither."""
        trip = frappe.copy_doc(frappe.get_test_records("Dispatch Trip")[0])
        trip.odometer_start = 100
        trip.odometer_end = None
        self.assertRaisesRegex(
            frappe.ValidationError,
            "must be set together",
            trip.insert,
        )

    def test_odometer_end_before_start_is_refused(self):
        """A trip cannot end behind where it started."""
        trip = frappe.copy_doc(frappe.get_test_records("Dispatch Trip")[0])
        trip.odometer_start = 200
        trip.odometer_end = 100
        self.assertRaisesRegex(
            frappe.ValidationError,
            "cannot be less than start",
            trip.insert,
        )

    def test_odometer_end_equal_to_start_is_accepted(self):
        """A zero-distance leg is degenerate, not backwards, and must be allowed to save."""
        trip = frappe.copy_doc(frappe.get_test_records("Dispatch Trip")[0])
        trip.odometer_start = 100
        trip.odometer_end = 100
        trip.insert()
        self.assertEqual(trip.odometer_end, 100)

    def test_marking_a_trip_completed_without_completion_notes_is_refused(self):
        """A Completed trip with no notes tells the fleet office nothing about what happened."""
        trip = frappe.copy_doc(frappe.get_test_records("Dispatch Trip")[0])
        trip.insert()
        trip.status = "Completed"
        trip.completion_notes = None
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Completion Notes are required",
            trip.save,
        )

    def test_submitting_a_trip_with_no_vehicle_is_refused(self):
        """Dispatch readiness checks vehicle first: nothing to drive means nothing to submit."""
        trip = frappe.copy_doc(frappe.get_test_records("Dispatch Trip")[0])
        trip.insert()
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Dispatch readiness: Vehicle is required",
            trip.submit,
        )

    def test_submitting_a_trip_with_no_project_is_refused(self):
        """A trip with a vehicle, driver and date but no project still has no cost owner."""
        trip = frappe.copy_doc(frappe.get_test_records("Dispatch Trip")[0])
        trip.vehicle = "VEH-000001"
        trip.driver = "DRV-000001"
        trip.insert()
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Dispatch readiness: Project is required",
            trip.submit,
        )

    def test_the_dispatch_to_completion_cycle_advances_the_vehicle_odometer(self):
        """The whole point of recording a completed trip's odometer is that the vehicle's own reading follows it."""
        project = frappe.db.get_value("Project", {"project_name": "_Test Project"})

        trip = frappe.copy_doc(frappe.get_test_records("Dispatch Trip")[0])
        trip.vehicle = "VEH-000001"
        trip.driver = "DRV-000001"
        trip.project = project
        trip.trip_date = nowdate()
        trip.append("stops", {"stop_name": "Test Stop"})
        trip.append("boarding_state", {"passenger_name": "Test Passenger"})
        trip.insert()

        dispatched = apply_workflow(trip, "Dispatch")
        self.assertEqual(dispatched.status, "Dispatched")

        dispatched.odometer_start = 1000
        dispatched.odometer_end = 1250
        dispatched.completion_notes = "Round trip completed without incident."
        dispatched.save()

        completed = apply_workflow(dispatched, "Complete")
        self.assertEqual(completed.status, "Completed")
        self.assertEqual(completed.docstatus, 1)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", "VEH-000001", "odometer"), 1250)
