# Copyright (c) 2026, afmcoltd
"""What a Salis Driver guarantees, asserted against the DocType itself.

A new driver is always forced to Active regardless of what status was typed
in, and once created, ``status`` and ``current_vehicle`` are machine-owned
mirrors: Driver Suspension/Driver Clearance own the first, Vehicle Assignment
owns the second, and a hand edit to either is refused. The sanctioned writers
use ``frappe.db.set_value``, which this test does not use, so it never
exercises a path that would legitimately bypass these guards.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle"]


class TestSalisDriver(FrappeTestCase):
    def test_a_new_driver_is_always_created_active_regardless_of_input(self):
        """Suspension and clearance are the only legitimate ways off Active, even at creation."""
        driver = frappe.copy_doc(frappe.get_test_records("Salis Driver")[0])
        driver.full_name = "_T-New Driver Status Test"
        driver.status = "Stopped"
        driver.insert()
        self.assertEqual(driver.status, "Active")

    def test_editing_status_by_hand_on_an_existing_driver_is_refused(self):
        """Status is written by Driver Suspension/Driver Clearance, never by a plain save."""
        driver = frappe.copy_doc(frappe.get_test_records("Salis Driver")[0])
        driver.full_name = "_T-Status Edit Test Driver"
        driver.insert()
        driver.status = "Stopped"
        self.assertRaisesRegex(
            frappe.PermissionError,
            "not by editing it",
            driver.save,
        )

    def test_setting_current_vehicle_by_hand_at_creation_is_refused(self):
        """current_vehicle is Vehicle Assignment's mirror, refused even on a brand-new driver."""
        driver = frappe.copy_doc(frappe.get_test_records("Salis Driver")[0])
        driver.full_name = "_T-New Driver Vehicle Test"
        driver.current_vehicle = "VEH-000001"
        self.assertRaisesRegex(
            frappe.PermissionError,
            "not by typing it here",
            driver.insert,
        )

    def test_editing_current_vehicle_by_hand_on_an_existing_driver_is_refused(self):
        """current_vehicle is set by assigning the driver, never by a plain save."""
        driver = frappe.copy_doc(frappe.get_test_records("Salis Driver")[0])
        driver.full_name = "_T-Existing Driver Vehicle Test"
        driver.insert()
        driver.current_vehicle = "VEH-000001"
        self.assertRaisesRegex(
            frappe.PermissionError,
            "not by editing it",
            driver.save,
        )
