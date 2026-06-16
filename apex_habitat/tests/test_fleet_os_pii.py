"""Regression test for the get_fleet_os PII permlevel gate (guards fix 1013da5).

Driver phone and external id (``driver_id``) are permlevel-1 fields on Salis
Driver. ``get_fleet_os`` must return them ONLY to a user who holds permlevel-1
read on Salis Driver (Fleet Manager / System Manager) and must blank them for a
role without it — otherwise the dashboard leaks PII to lower fleet roles, the
exact defect the skeptics audit caught.

The no-PII assertion is deliberately NON-VACUOUS: the viewer is an Internal
Auditor, an UNSCOPED oversight role, so it still sees every vehicle. The vehicle
is therefore present in the response and only its driver PII is stripped — if a
future refactor drops the gate, ``mobile``/``driver_id`` would come back and the
test fails (rather than passing because the row vanished).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api.fleet_os import get_fleet_os

# [#hdpjau]
# [#b3us0i]
PHONE = "0500000000"


class TestFleetOsPIIGate(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _seed_vehicle(self):
        """A driver carrying PII, mirrored onto a vehicle as its current driver.
        Keyed off the test method so plate_normalized / driver_id stay unique."""
        tag = self._testMethodName  # [#ryvrub]
        ext_id = "PIID-" + tag
        driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": "PII Gate Driver",
                "driver_id": ext_id,
                "phone": PHONE,
            }
        ).insert(ignore_permissions=True)
        plate = "PIIGATE " + tag
        frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": plate,
                "status": "Active",
                "current_driver": driver.name,
            }
        ).insert(ignore_permissions=True)
        return plate, ext_id

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

    def _current_driver(self, plate):
        for v in get_fleet_os().get("vehicles", []):
            if v.get("plate") == plate:
                return v.get("current_driver")
        return None

    def test_pii_shown_to_permlevel1_role(self):
        plate, ext_id = self._seed_vehicle()
        frappe.set_user("Administrator")  # [#pg0epd]
        cd = self._current_driver(plate)
        self.assertIsNotNone(cd, "the seeded vehicle must surface for System Manager")
        self.assertEqual(cd["mobile"], PHONE, "permlevel-1 role must see the phone")
        self.assertEqual(cd["driver_id"], ext_id, "permlevel-1 role must see the external id")

    def test_pii_hidden_from_non_permlevel1_role(self):
        plate, _ext_id = self._seed_vehicle()
        frappe.set_user(self._auditor_user())  # [#8yrk2t]
        cd = self._current_driver(plate)
        self.assertIsNotNone(cd, "the vehicle must STILL be visible (non-vacuous check)")
        self.assertEqual(cd["mobile"], "", "phone must be blanked without permlevel-1 read")
        self.assertEqual(cd["driver_id"], "", "external id must be blanked without permlevel-1 read")
