# Copyright (c) 2026, afmcoltd
"""What a Driver Suspension guarantees, asserted against the DocType itself.

A stop that asks to release a vehicle must name which one. A stop for
Violation or Termination cannot submit without evidence. A driver who still
has a planned (not yet dispatched) trip cannot be stopped at all — the check
runs at save time, not only at submit, so the operator is told while still
filling the form. Submitting a stop moves the driver to Stopped and records
their prior status; cancelling restores it.

The planned-trip case gets its own driver (DRV-000002) so the Dispatch Trip it
creates as setup does not leak into the other tests in this class — nothing
rolls back between test methods (``FrappeTestCase`` rolls back only once, at
class teardown), and every other test here uses DRV-000001.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days

test_dependencies = ["Salis Driver", "Salis Vehicle"]


class TestDriverSuspension(FrappeTestCase):
    def test_a_driver_with_a_planned_trip_cannot_be_stopped(self):
        """Stopping a driver mid-assignment must be refused until the trip is reassigned."""
        trip = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "trip_type": "Ad Hoc",
                "trip_date": add_days(frappe.utils.nowdate(), 5),
                "driver": "DRV-000002",
                "status": "Planned",
            }
        )
        trip.insert()

        suspension = frappe.copy_doc(frappe.get_test_records("Driver Suspension")[0])
        suspension.driver = "DRV-000002"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "still has 1 planned trip",
            suspension.insert,
        )

    def test_releasing_a_vehicle_without_naming_it_is_refused(self):
        """A release with no vehicle named cannot release anything."""
        suspension = frappe.copy_doc(frappe.get_test_records("Driver Suspension")[0])
        suspension.release_vehicle = 1
        suspension.related_vehicle = None
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Select the vehicle to release",
            suspension.insert,
        )

    def test_submitting_a_violation_stop_without_evidence_is_refused(self):
        """A Violation stop must be backed by evidence before it can take effect."""
        suspension = frappe.copy_doc(frappe.get_test_records("Driver Suspension")[0])
        suspension.stop_reason = "Violation"
        suspension.evidence = None
        suspension.insert()
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Evidence is required",
            suspension.submit,
        )

    def test_submitting_a_stop_moves_the_driver_to_stopped_and_cancel_restores_it(self):
        """Stop and its cancel are the two real effects this DocType exists to have."""
        suspension = frappe.copy_doc(frappe.get_test_records("Driver Suspension")[0])
        suspension.insert()
        suspension.submit()
        self.assertEqual(frappe.db.get_value("Salis Driver", "DRV-000001", "status"), "Stopped")

        suspension.cancel()
        self.assertEqual(frappe.db.get_value("Salis Driver", "DRV-000001", "status"), "Active")
