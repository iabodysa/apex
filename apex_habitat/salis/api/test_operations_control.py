"""Tests for the Fleet Control export.

``export_fleet`` re-runs the scoped board query server-side and streams it as a
native csv response, so the file holds the FULL permission-/scope-consistent
result rather than only the rows a client happened to paint. The project-scope
resolver is patched so the export's scope can be asserted deterministically on a
fresh site.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex_habitat.salis.api import operations_control

# get_fleet resolves scope through the shared fleet_reader service, so the
# project-scope resolver is patched there (its single home).
_RESOLVER = "apex_habitat.salis.api.fleet_reader._permitted_projects"


class TestExportFleet(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.local.response = frappe._dict()
        self.plate = f"EXP {frappe.generate_hash(length=6)}"
        self.vehicle = (
            frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": self.plate, "status": "Active"})
            .insert(ignore_permissions=True)
            .name
        )

    def _csv(self):
        # build_csv_response writes the file body into frappe.response["result"].
        self.assertEqual(frappe.response.get("type"), "csv")
        return frappe.response.get("result") or ""

    def test_unscoped_export_streams_csv_with_vehicle(self):
        with patch(_RESOLVER, return_value=(True, None)):
            operations_control.export_fleet()
        body = self._csv()
        self.assertIn("Plate", body)  # header row present
        self.assertIn(self.plate, body)  # the vehicle is in the file

    def test_export_respects_server_side_scope(self):
        # Scoped to a project that does not own this vehicle: the export must omit
        # it even though it exists, proving scope is enforced server-side.
        ghost = f"NO-SUCH-PROJECT-{frappe.generate_hash(length=10)}"
        with patch(_RESOLVER, return_value=(False, [ghost])):
            operations_control.export_fleet()
        body = self._csv()
        self.assertIn("Plate", body)
        self.assertNotIn(self.plate, body)


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
