# Copyright (c) 2026, AFMCO and contributors
"""End-to-end guard for the Fleet OS console write actions (salis/api/fleet_os.py).

Two properties must hold:

  1. Each action produces the CORRECT effect — reassign submits a Vehicle Assignment, stop
     submits a Vehicle Suspension and stops the vehicle, and workshop_in/out + recover move
     the vehicle status — so a refactor that wires an action to the wrong DocType or status
     fails here.
  2. Every action is permission-gated on Salis Vehicle "write" (via ``_resolve_plate``): a
     read-only role (Internal Auditor) is refused on all of them.

The vehicle and driver are borrowed from the shipped fixtures and handed back after each
case. The theft cases that once lived here are gone rather than converted: ``report_theft``
is part of the console surface retired on purpose, which
``apex/www/test_portal_shell_contract.py`` forbids from returning.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api.fleet_os import (
    reassign,
    recover,
    stop_vehicle,
    workshop_in,
    workshop_out,
)

test_dependencies = ["Salis Vehicle", "Salis Driver"]

PLATE = "_T ABC 1001"
DRIVER_NAME = "_Test Driver"


class TestFleetOsActions(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # Registered LIFO: the session is handed back to Administrator FIRST, so the
        # restore that follows it runs with the rights to cancel what the case submitted.
        self.addCleanup(self._restore)
        self.addCleanup(frappe.set_user, "Administrator")
        self.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": PLATE}, "name")
        self.driver = frappe.db.get_value("Salis Driver", {"full_name": DRIVER_NAME}, "name")
        frappe.db.set_value("Salis Vehicle", self.vehicle, "current_driver", self.driver)

    def _restore(self):
        """Hand the borrowed vehicle back: cancel the stops the actions submitted (whose
        on_cancel restores the previous status) and clear the mirrored driver links."""
        for stop in frappe.get_all(
            "Vehicle Suspension", filters={"vehicle": self.vehicle, "docstatus": 1}, pluck="name"
        ):
            frappe.get_doc("Vehicle Suspension", stop).cancel()
        frappe.db.set_value("Salis Vehicle", self.vehicle, {"status": "Active", "current_driver": None})
        frappe.db.set_value("Salis Driver", self.driver, "current_vehicle", None)

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
        res = reassign(PLATE, self.driver)
        self.assertTrue(res.get("ok"))
        va = res.get("assignment")
        self.assertTrue(va, "reassign must return the new Vehicle Assignment name")
        self.assertEqual(
            frappe.db.get_value("Vehicle Assignment", va, "docstatus"), 1, "the assignment must be submitted"
        )
        self.assertEqual(frappe.db.get_value("Vehicle Assignment", va, "driver"), self.driver)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", self.vehicle, "current_driver"), self.driver)
        self.assertEqual(frappe.db.get_value("Salis Driver", self.driver, "current_vehicle"), self.vehicle)

    def test_stop_submits_vehicle_stop_and_stops_vehicle(self):
        res = stop_vehicle(PLATE, reason="accident")
        self.assertTrue(res.get("ok"))
        self.assertEqual(
            frappe.db.get_value("Vehicle Suspension", res.get("stop"), "docstatus"), 1,
            "the stop must be submitted",
        )
        self.assertEqual(frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Stopped")

    def test_workshop_and_recover_move_vehicle_status(self):
        workshop_in(PLATE)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Under Maintenance")
        workshop_out(PLATE)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Active")
        stop_vehicle(PLATE)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Stopped")
        recover(PLATE)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Active")

    def test_all_actions_gated_on_vehicle_write(self):
        frappe.set_user(self._auditor_user())
        calls = (
            lambda: reassign(PLATE, self.driver),
            lambda: stop_vehicle(PLATE),
            lambda: workshop_in(PLATE),
            lambda: workshop_out(PLATE),
            lambda: recover(PLATE),
        )
        for call in calls:
            with self.assertRaises(frappe.PermissionError):
                call()
