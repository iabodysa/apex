# Copyright (c) 2026, AFMCO and contributors
"""End-to-end guard for the Fleet OS console write actions (salis/api/fleet_os.py).

The dashboard's operations console drives six whitelisted POST actions. Two
properties must hold and were previously untested (test_salis_fleet_scope covers
row-scoping and test_fleet_os_pii covers the read PII gate — neither the writes):

  1. Each action produces the CORRECT effect — reassign submits a Vehicle
     Assignment, stop submits a Vehicle Stop and stops the vehicle, report_theft
     submits a Theft Vehicle Incident, and workshop_in/out + recover move the
     vehicle status — so a refactor that wires an action to the wrong DocType or
     status fails here.
  2. Every action is permission-gated on Salis Vehicle "write" (via
     _resolve_plate): a read-only role (Internal Auditor) is refused on all six.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api.fleet_os import (
    reassign,
    recover,
    report_theft,
    stop_vehicle,
    workshop_in,
    workshop_out,
)


class TestFleetOsActions(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _seed(self):
        """A driver mirrored onto an active vehicle; keyed off the test method so
        plate_number / driver_id stay unique per test."""
        tag = self._testMethodName
        ext_id = "FOA-" + tag
        driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": "Fleet Action Driver",
                "driver_id": ext_id,
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        plate = "FLEETOPS " + tag
        frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": plate,
                "status": "Active",
                "current_driver": driver.name,
            }
        ).insert(ignore_permissions=True)
        return plate, driver.name, ext_id

    def _name(self, plate):
        return frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")

    def _auditor_user(self):
        """A read-only oversight role: read but NOT write on Salis Vehicle, so the
        console's _resolve_plate write-gate (not row scope) is what refuses it."""
        email = "fleet-actions-auditor@test.local"
        if not frappe.db.exists("User", email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": "Fleet Actions Auditor",
                    "roles": [{"role": "Internal Auditor"}],
                }
            ).insert(ignore_permissions=True)
        return email

    def test_reassign_submits_vehicle_assignment(self):
        plate, driver, ext_id = self._seed()
        res = reassign(plate, ext_id)
        self.assertTrue(res.get("ok"))
        va = res.get("assignment")
        self.assertTrue(va, "reassign must return the new Vehicle Assignment name")
        self.assertEqual(
            frappe.db.get_value("Vehicle Assignment", va, "docstatus"), 1, "the assignment must be submitted"
        )
        self.assertEqual(frappe.db.get_value("Vehicle Assignment", va, "driver"), driver)
        name = self._name(plate)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", name, "current_driver"), driver)
        self.assertEqual(frappe.db.get_value("Salis Driver", driver, "current_vehicle"), name)

    def test_stop_submits_vehicle_stop_and_stops_vehicle(self):
        plate, _driver, _ext = self._seed()
        res = stop_vehicle(plate, reason="accident")
        self.assertTrue(res.get("ok"))
        self.assertEqual(
            frappe.db.get_value("Vehicle Stop", res.get("stop"), "docstatus"), 1, "the stop must be submitted"
        )
        self.assertEqual(frappe.db.get_value("Salis Vehicle", self._name(plate), "status"), "Stopped")

    def test_report_theft_submits_incident_and_stops_vehicle(self):
        plate, _driver, _ext = self._seed()
        res = report_theft(plate, location="Gate 4")
        self.assertTrue(res.get("ok"))
        inc = res.get("incident")
        self.assertEqual(frappe.db.get_value("Vehicle Incident", inc, "incident_type"), "Theft")
        self.assertEqual(frappe.db.get_value("Vehicle Incident", inc, "docstatus"), 1)
        name = self._name(plate)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", name, "status"), "Stopped")
        self.assertFalse(
            frappe.db.get_value("Salis Vehicle", name, "current_driver"), "a theft must release the driver"
        )

    def test_recover_closes_the_open_theft_incident(self):
        plate, driver, _ext = self._seed()
        name = self._name(plate)

        theft = report_theft(plate, location="Gate 4").get("incident")
        self.assertEqual(frappe.db.get_value("Salis Vehicle", name, "status"), "Stopped")

        res = recover(plate)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("incident"), theft, "recover must report the theft it closed")
        # [#j0taee]
        self.assertEqual(frappe.db.get_value("Vehicle Incident", theft, "status"), "Closed")
        # [#7hgts7]
        self.assertEqual(frappe.db.get_value("Salis Vehicle", name, "status"), "Active")
        self.assertEqual(frappe.db.get_value("Salis Vehicle", name, "current_driver"), driver)
        self.assertEqual(frappe.db.get_value("Salis Driver", driver, "current_vehicle"), name)

    def test_workshop_and_recover_move_vehicle_status(self):
        plate, _driver, _ext = self._seed()
        name = self._name(plate)
        workshop_in(plate)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", name, "status"), "Under Maintenance")
        workshop_out(plate)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", name, "status"), "Active")
        stop_vehicle(plate)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", name, "status"), "Stopped")
        recover(plate)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", name, "status"), "Active")

    def test_all_actions_gated_on_vehicle_write(self):
        plate, _driver, ext_id = self._seed()
        frappe.set_user(self._auditor_user())
        calls = (
            lambda: reassign(plate, ext_id),
            lambda: stop_vehicle(plate),
            lambda: report_theft(plate),
            lambda: workshop_in(plate),
            lambda: workshop_out(plate),
            lambda: recover(plate),
        )
        for call in calls:
            with self.assertRaises(frappe.PermissionError):
                call()
