# Copyright (c) 2026, afmcoltd
"""What a Vehicle Assignment guarantees, asserted against the DocType itself.

An end date cannot precede the start date. A vehicle (or a driver) already
holding an active, submitted assignment cannot be double-booked into an
overlapping one. Submitting the assignment is what actually pairs the vehicle
and driver (denormalized onto both masters); cancelling clears that pairing.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle", "Salis Driver", "Project"]


class TestVehicleAssignment(FrappeTestCase):
    def test_an_end_date_before_the_start_date_is_refused(self):
        """An assignment cannot end before it starts."""
        assignment = frappe.copy_doc(frappe.get_test_records("Vehicle Assignment")[0])
        assignment.start_date = "2026-03-10"
        assignment.end_date = "2026-03-01"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "cannot be earlier than Start Date",
            assignment.insert,
        )

    def test_an_overlapping_active_assignment_for_the_same_vehicle_is_refused(self):
        """One vehicle cannot be actively assigned to two overlapping periods at once."""
        first = frappe.copy_doc(frappe.get_test_records("Vehicle Assignment")[0])
        first.start_date = "2026-04-01"
        first.end_date = "2026-04-30"
        first.insert()
        first.submit()

        second = frappe.copy_doc(frappe.get_test_records("Vehicle Assignment")[0])
        second.driver = "DRV-000002"
        second.start_date = "2026-04-15"
        second.end_date = "2026-05-15"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "already has an active assignment",
            second.insert,
        )

    def test_submitting_pairs_the_vehicle_and_driver_and_cancel_clears_it(self):
        """Pairing (and unpairing) both masters is the entire point of this DocType."""
        assignment = frappe.copy_doc(frappe.get_test_records("Vehicle Assignment")[0])
        assignment.start_date = "2026-05-01"
        assignment.end_date = "2026-05-31"
        assignment.insert()
        assignment.submit()

        self.assertEqual(frappe.db.get_value("Salis Vehicle", "VEH-000001", "current_driver"), "DRV-000001")
        self.assertEqual(frappe.db.get_value("Salis Driver", "DRV-000001", "current_vehicle"), "VEH-000001")

        assignment.cancel()
        self.assertIsNone(frappe.db.get_value("Salis Vehicle", "VEH-000001", "current_driver"))
        self.assertIsNone(frappe.db.get_value("Salis Driver", "DRV-000001", "current_vehicle"))
