# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Fleet Control guided driver reassignment."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.salis.api import fleet_os, operations_control


class TestReassignDriver(FrappeTestCase):
    """reassign_driver ends the current Active Vehicle Assignment and starts a new
    one through the native submit lifecycle (which stamps current_driver)."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.vehicle = (
            frappe.get_doc(
                {
                    "doctype": "Salis Vehicle",
                    "plate_number": f"RA {frappe.generate_hash(length=12)}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.driver_a = self._driver()
        self.driver_b = self._driver()
        # [#417x1z]
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
                    "full_name": f"Rider {frappe.generate_hash(length=12)}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def test_reassign_ends_old_and_stamps_new_driver(self):
        out = operations_control.reassign_driver(vehicle=self.vehicle, driver=self.driver_b)
        self.assertTrue(out["ok"])
        # [#jhsafp]
        new = frappe.get_doc("Vehicle Assignment", out["assignment"])
        self.assertEqual(new.driver, self.driver_b)
        self.assertEqual(new.status, "Active")
        # [#1nh1te]
        self.assertEqual(frappe.db.get_value("Vehicle Assignment", self.first.name, "status"), "Ended")
        # [#99wbp9]
        self.assertEqual(frappe.db.get_value("Salis Vehicle", self.vehicle, "current_driver"), self.driver_b)
        self.assertEqual(frappe.db.get_value("Salis Driver", self.driver_b, "current_vehicle"), self.vehicle)

    def test_reassign_to_same_driver_is_rejected(self):
        # [#rme102]
        with self.assertRaises(frappe.ValidationError):
            operations_control.reassign_driver(vehicle=self.vehicle, driver=self.driver_a)
        # [#nquaxn]
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

    def _vehicle(self):
        return (
            frappe.get_doc(
                {
                    "doctype": "Salis Vehicle",
                    "plate_number": f"PAR {frappe.generate_hash(length=12)}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
        )

    def _driver(self):
        return frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": f"Rider {frappe.generate_hash(length=12)}",
                "driver_id": f"PARD-{frappe.generate_hash(length=12)}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)

    def test_reassign_reaches_same_outcome_on_both_surfaces(self):
        # [#p16c3w]
        v1, d1 = self._vehicle(), self._driver()
        fleet_os.reassign(v1.plate_number, d1.driver_id)
        # [#hx8sp9]
        v2, d2 = self._vehicle(), self._driver()
        operations_control.reassign_driver(vehicle=v2.name, driver=d2.name)

        # [#flm26p]
        for veh, drv in ((v1.name, d1.name), (v2.name, d2.name)):
            self.assertEqual(frappe.db.get_value("Salis Vehicle", veh, "current_driver"), drv)
            self.assertEqual(frappe.db.get_value("Salis Driver", drv, "current_vehicle"), veh)
            self.assertTrue(
                frappe.db.exists(
                    "Vehicle Assignment",
                    {"vehicle": veh, "driver": drv, "status": "Active", "docstatus": 1},
                )
            )

    def test_stop_close_reaches_same_outcome_on_both_surfaces(self):
        # [#7v5ry5]
        v1 = self._vehicle()
        fleet_os.workshop_in(v1.plate_number)
        ws_stop = frappe.db.get_value(
            "Vehicle Stop",
            {"vehicle": v1.name, "stop_reason": "Maintenance", "docstatus": 1},
            "name",
        )
        fleet_os.workshop_out(v1.plate_number)

        # [#m3jjqg]
        v2 = self._vehicle()
        stop_doc = frappe.get_doc(
            {
                "doctype": "Vehicle Stop",
                "vehicle": v2.name,
                "stop_reason": "Other",
                "stop_date": today(),
            }
        ).insert(ignore_permissions=True)
        stop_doc.submit()
        operations_control.release_vehicle(vehicle=v2.name)

        # [#8r83c0]
        for stop_name, veh in ((ws_stop, v1.name), (stop_doc.name, v2.name)):
            self.assertEqual(frappe.db.get_value("Vehicle Stop", stop_name, "docstatus"), 2)
            self.assertTrue(frappe.db.get_value("Vehicle Stop", stop_name, "return_date"))
            self.assertEqual(frappe.db.get_value("Salis Vehicle", veh, "status"), "Active")
