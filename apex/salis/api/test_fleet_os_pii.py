# Copyright (c) 2026, AFMCO and contributors
"""Regression test for the get_fleet_os PII permlevel gate (guards fix 1013da5).

Driver phone and external id (``driver_id``) are permlevel-1 fields on Salis
Driver. ``get_fleet_os`` must return them ONLY to a user who holds permlevel-1
read on Salis Driver (Fleet Manager / System Manager) and must blank them for a
role without it — otherwise the dashboard leaks PII to lower fleet roles, the
exact defect the skeptics audit caught.

The no-PII assertion is deliberately NON-VACUOUS: the viewer is an Internal
Auditor, an UNSCOPED oversight role, so it still sees every vehicle. The vehicle
is therefore present in the response and only its driver PII is stripped.

The vehicle and driver come from the shipped fixtures. Only the two PII values are
written onto the borrowed driver, and both are handed back after each case.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api.fleet_os import get_fleet_os

test_dependencies = ["Salis Vehicle", "Salis Driver"]

PLATE = "_T ABC 1001"
DRIVER_NAME = "_Test Driver"
PHONE = "0500000000"
EXTERNAL_ID = "PIID-_T-ABC-1001"


class TestFleetOsPIIGate(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        self.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": PLATE}, "name")
        self.driver = frappe.db.get_value("Salis Driver", {"full_name": DRIVER_NAME}, "name")

        self.addCleanup(
            frappe.db.set_value, "Salis Driver", self.driver, {"phone": None, "driver_id": None}
        )
        self.addCleanup(frappe.db.set_value, "Salis Vehicle", self.vehicle, "current_driver", None)
        frappe.db.set_value(
            "Salis Driver", self.driver, {"phone": PHONE, "driver_id": EXTERNAL_ID}
        )
        frappe.db.set_value("Salis Vehicle", self.vehicle, "current_driver", self.driver)

    def _auditor_user(self):
        """An unscoped role WITHOUT permlevel-1 read on Salis Driver, so the
        permlevel gate (not project scope) is what blanks the PII."""
        email = "pii-gate-auditor@test.local"
        if not frappe.db.exists("User", email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": "PII Gate Auditor",
                    "roles": [{"role": "Internal Auditor"}],
                }
            ).insert(ignore_permissions=True)
        return email

    def _current_driver(self):
        for v in get_fleet_os().get("vehicles", []):
            if v.get("plate") == PLATE:
                return v.get("current_driver")
        return None

    def test_pii_shown_to_permlevel1_role(self):
        cd = self._current_driver()
        self.assertIsNotNone(cd, "the fixture vehicle must surface for System Manager")
        self.assertEqual(cd["mobile"], PHONE, "permlevel-1 role must see the phone")
        self.assertEqual(cd["driver_id"], EXTERNAL_ID, "permlevel-1 role must see the external id")

    def test_pii_hidden_from_non_permlevel1_role(self):
        frappe.set_user(self._auditor_user())
        cd = self._current_driver()
        self.assertIsNotNone(cd, "the vehicle must STILL be visible (non-vacuous check)")
        self.assertEqual(cd["mobile"], "", "phone must be blanked without permlevel-1 read")
        self.assertEqual(cd["driver_id"], "", "external id must be blanked without permlevel-1 read")
