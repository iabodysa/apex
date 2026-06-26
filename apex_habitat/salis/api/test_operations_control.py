"""Tests for the Fleet Control guided driver reassignment."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex_habitat.salis.api import operations_control


class TestReassignDriver(FrappeTestCase):
    """reassign_driver ends the current Active Vehicle Assignment and starts a new
    one through the native submit lifecycle (which stamps current_driver)."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.vehicle = (
            frappe.get_doc(
                {
                    "doctype": "Salis Vehicle",
                    "plate_number": f"RA {frappe.generate_hash(length=6)}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.driver_a = self._driver()
        self.driver_b = self._driver()
        # Seed a current assignment so reassign has an Active one to end.
        self.first = (
            frappe.get_doc(
                {
                    "doctype": "Vehicle Assignment",
                    "vehicle": self.vehicle,
                    "driver": self.driver_a,
                    "start_date": today(),
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
        )
        self.first.submit()

    def _driver(self):
        return (
            frappe.get_doc(
                {
                    "doctype": "Salis Driver",
                    "full_name": f"Rider {frappe.generate_hash(length=6)}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def test_reassign_ends_old_and_stamps_new_driver(self):
        out = operations_control.reassign_driver(vehicle=self.vehicle, driver=self.driver_b)
        self.assertTrue(out["ok"])
        # New assignment is Active and points at the new driver.
        new = frappe.get_doc("Vehicle Assignment", out["assignment"])
        self.assertEqual(new.driver, self.driver_b)
        self.assertEqual(new.status, "Active")
        # The previous assignment is Ended (no longer Active).
        self.assertEqual(frappe.db.get_value("Vehicle Assignment", self.first.name, "status"), "Ended")
        # The native on_submit stamped the denormalized links to the new driver.
        self.assertEqual(frappe.db.get_value("Salis Vehicle", self.vehicle, "current_driver"), self.driver_b)
        self.assertEqual(frappe.db.get_value("Salis Driver", self.driver_b, "current_vehicle"), self.vehicle)

    def test_reassign_to_same_driver_is_rejected(self):
        # Reassigning to the driver already on the vehicle is a no-op and must throw
        # rather than silently create a duplicate Active assignment.
        with self.assertRaises(frappe.ValidationError):
            operations_control.reassign_driver(vehicle=self.vehicle, driver=self.driver_a)
        # The original assignment is untouched (still Active).
        self.assertEqual(frappe.db.get_value("Vehicle Assignment", self.first.name, "status"), "Active")

    def test_reassign_requires_a_driver(self):
        with self.assertRaises(frappe.ValidationError):
            operations_control.reassign_driver(vehicle=self.vehicle, driver=None)
