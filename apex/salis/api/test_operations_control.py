# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Fleet Control guided driver reassignment.

The two vehicles and the two drivers are the shipped fixtures. Only the Vehicle
Assignment each case reassigns FROM is built here, because that assignment is the
subject; every borrowed record is handed back afterwards.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.salis.api import fleet_os, operations_control

test_dependencies = ["Salis Vehicle", "Salis Driver"]

PLATE_A = "_T ABC 1001"
PLATE_B = "_T ABC 1002"
DRIVER_A = "_Test Driver"
DRIVER_B = "_Test Driver Two"


def _vehicle(plate):
    return frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")


def _driver(full_name):
    return frappe.db.get_value("Salis Driver", {"full_name": full_name}, "name")


def _release(vehicles, drivers):
    """Hand the borrowed pairing back: cancel every assignment and stop the case
    submitted, then clear the denormalized current_driver / current_vehicle mirrors."""
    for vehicle in vehicles:
        for doctype in ("Vehicle Assignment", "Vehicle Suspension"):
            for name in frappe.get_all(
                doctype, filters={"vehicle": vehicle, "docstatus": 1}, pluck="name"
            ):
                frappe.get_doc(doctype, name).cancel()
        frappe.db.set_value(
            "Salis Vehicle", vehicle, {"status": "Active", "current_driver": None}
        )
    for driver in drivers:
        frappe.db.set_value("Salis Driver", driver, "current_vehicle", None)


class TestReassignDriver(FrappeTestCase):
    """reassign_driver ends the current Active Vehicle Assignment and starts a new
    one through the native submit lifecycle (which stamps current_driver)."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.vehicle = _vehicle(PLATE_A)
        self.driver_a = _driver(DRIVER_A)
        self.driver_b = _driver(DRIVER_B)
        self.addCleanup(_release, [self.vehicle], [self.driver_a, self.driver_b])

        self.first = frappe.get_doc(
            {
                "doctype": "Vehicle Assignment",
                "vehicle": self.vehicle,
                "driver": self.driver_a,
                "start_date": today(),
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        self.first.submit()

    def test_reassign_ends_old_and_stamps_new_driver(self):
        out = operations_control.reassign_driver(vehicle=self.vehicle, driver=self.driver_b)
        self.assertTrue(out["ok"])
        new = frappe.get_doc("Vehicle Assignment", out["assignment"])
        self.assertEqual(new.driver, self.driver_b)
        self.assertEqual(new.status, "Active")
        self.assertEqual(frappe.db.get_value("Vehicle Assignment", self.first.name, "status"), "Ended")
        self.assertEqual(frappe.db.get_value("Salis Vehicle", self.vehicle, "current_driver"), self.driver_b)
        self.assertEqual(frappe.db.get_value("Salis Driver", self.driver_b, "current_vehicle"), self.vehicle)

    def test_reassign_to_same_driver_is_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            operations_control.reassign_driver(vehicle=self.vehicle, driver=self.driver_a)
        self.assertEqual(frappe.db.get_value("Vehicle Assignment", self.first.name, "status"), "Active")

    def test_reassign_requires_a_driver(self):
        with self.assertRaises(frappe.ValidationError):
            operations_control.reassign_driver(vehicle=self.vehicle, driver=None)


class TestSupervisorSurfaceParity(FrappeTestCase):
    """The /fleet board (fleet_os) and the Fleet Control drawer (operations_control)
    drive reassign and stop-close through ONE shared helper, so the two surfaces
    reach the same assignment/stop outcome for the same action."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.v1, self.v2 = _vehicle(PLATE_A), _vehicle(PLATE_B)
        self.d1, self.d2 = _driver(DRIVER_A), _driver(DRIVER_B)
        self.addCleanup(_release, [self.v1, self.v2], [self.d1, self.d2])

    def test_reassign_reaches_same_outcome_on_both_surfaces(self):
        fleet_os.reassign(PLATE_A, self.d1)
        operations_control.reassign_driver(vehicle=self.v2, driver=self.d2)

        for veh, drv in ((self.v1, self.d1), (self.v2, self.d2)):
            self.assertEqual(frappe.db.get_value("Salis Vehicle", veh, "current_driver"), drv)
            self.assertEqual(frappe.db.get_value("Salis Driver", drv, "current_vehicle"), veh)
            self.assertTrue(
                frappe.db.exists(
                    "Vehicle Assignment",
                    {"vehicle": veh, "driver": drv, "status": "Active", "docstatus": 1},
                )
            )

    def test_stop_close_reaches_same_outcome_on_both_surfaces(self):
        fleet_os.workshop_in(PLATE_A)
        ws_stop = frappe.db.get_value(
            "Vehicle Suspension",
            {"vehicle": self.v1, "stop_reason": "Maintenance", "docstatus": 1},
            "name",
        )
        fleet_os.workshop_out(PLATE_A)

        stop_doc = frappe.get_doc(
            {
                "doctype": "Vehicle Suspension",
                "vehicle": self.v2,
                "stop_reason": "Other",
                "stop_date": today(),
            }
        ).insert(ignore_permissions=True)
        stop_doc.submit()
        operations_control.release_vehicle(vehicle=self.v2)

        for stop_name, veh in ((ws_stop, self.v1), (stop_doc.name, self.v2)):
            self.assertEqual(frappe.db.get_value("Vehicle Suspension", stop_name, "docstatus"), 2)
            self.assertTrue(frappe.db.get_value("Vehicle Suspension", stop_name, "return_date"))
            self.assertEqual(frappe.db.get_value("Salis Vehicle", veh, "status"), "Active")
