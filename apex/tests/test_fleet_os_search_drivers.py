# Copyright (c) 2026, AFMCO and contributors
"""Guards for the Fleet OS reassign driver picker (salis/api/fleet_os.search_drivers).

The reassign sub-form used to send a free-typed iqama as the driver id, so a typo
silently failed to resolve (or risked the wrong driver). The picker now binds the
canonical Salis Driver ``name`` returned here. Three properties must hold:

  1. A query finds active drivers by name (and by external id for a PII-bearing
     role) and returns the canonical ``name`` reassign resolves — so the typo gap
     is closed.
  2. The permlevel-1 PII gate matches get_fleet_os: ``driver_id``/``phone`` come
     back ONLY for a permlevel-1 role and are blanked otherwise. The no-PII check
     is NON-VACUOUS — the viewer is an unscoped Internal Auditor, so the driver
     row is still present; only its PII is stripped.
  3. Project scope is enforced: a scoped supervisor with no granted project gets
     an empty list (the scope_empty path), never the full driver table.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api.fleet_os import reassign, search_drivers
from apex.tests._helpers import _user

PHONE = "0500001234"


class TestFleetOsSearchDrivers(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # [#l5abyd]
        self.tag = frappe.generate_hash(length=8).upper()
        self.full_name = f"Picker Driver {self.tag}"
        self.ext_id = f"PICK-{self.tag}"
        self.driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": self.full_name,
                "driver_id": self.ext_id,
                "phone": PHONE,
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name

    def tearDown(self):
        frappe.set_user("Administrator")

    def _row(self, rows):
        return next((r for r in rows if r["name"] == self.driver), None)

    def test_finds_by_name_and_returns_canonical_name(self):
        row = self._row(search_drivers(q=self.full_name[:12]))
        self.assertIsNotNone(row, "an active driver must be found by name")
        self.assertEqual(row["name"], self.driver, "the canonical Salis Driver name backs the picker")
        self.assertEqual(row["full_name"], self.full_name)

    def test_finds_by_external_id_for_pii_role(self):
        # [#bdedv1]
        row = self._row(search_drivers(q=self.ext_id))
        self.assertIsNotNone(row, "a permlevel-1 role must match on the external id")

    def test_picked_name_resolves_in_reassign(self):
        # [#3a9ikc]
        plate = f"PICKVEH {self.tag}"
        frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
        ).insert(ignore_permissions=True)
        res = reassign(plate, self.driver)
        self.assertTrue(res.get("ok"))
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "current_driver"),
            self.driver,
            "reassign must bind the driver the picker selected",
        )

    def test_pii_blanked_for_non_permlevel1_role(self):
        auditor = _user("search-drivers-auditor@test.local", "Internal Auditor")
        frappe.set_user(auditor)
        row = self._row(search_drivers(q=self.full_name[:12]))
        # [#td16yx]
        self.assertIsNotNone(row, "the driver must still be visible (non-vacuous PII check)")
        self.assertEqual(row["driver_id"], "", "external id must be blanked without permlevel-1 read")
        self.assertEqual(row["phone"], "", "phone must be blanked without permlevel-1 read")

    def test_scoped_user_without_project_gets_empty(self):
        # [#si07ep]
        sup = _user("search-drivers-scoped@test.local", "Fleet Supervisor")
        frappe.db.delete("User Permission", {"user": sup, "allow": "Project"})
        frappe.set_user(sup)
        self.assertEqual(
            search_drivers(q=self.full_name[:12]), [], "a no-project supervisor must get no drivers"
        )
