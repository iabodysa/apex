"""Building-scope security for the Housing Supervisor (Resident Supervisor).

Verifies the contract of habitat.permissions building scoping without heavy
fixtures: the User-Permission lookup (_allowed_buildings) and role classification
(_building_is_unscoped) are thin frappe wrappers (mirroring the proven Salis
project scope), so they are stubbed; the security LOGIC — the WHERE fragment and
the per-document allow/deny branching — is exercised directly.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.habitat import permissions as P


class TestHousingSupervisorScope(FrappeTestCase):
    def test_scoped_supervisor_confined_to_his_buildings(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=["BLDG-1"]
        ):
            # [#m7luyx]
            cond = P._building_condition(user="sup")
            self.assertIn("BLDG-1", cond)
            self.assertIn("`building`", cond)

            def hp(dt, **kw):
                return P.building_scoped_has_permission(
                    frappe._dict(doctype=dt, **kw), "read", user="sup"
                )

            # [#ja5exi]
            self.assertIsNone(hp("Custody Issue", building="BLDG-1"))
            self.assertFalse(hp("Custody Issue", building="BLDG-2"))
            self.assertIsNone(hp("Accommodation Assignment", building="BLDG-1"))
            self.assertFalse(hp("Cleaning Log", building="BLDG-2"))
            # [#j2hedt]
            self.assertFalse(hp("Cleaning Log", building=None))
            # [#7ejbh2]
            self.assertIsNone(hp("Accommodation Building", name="BLDG-1"))
            self.assertFalse(hp("Accommodation Building", name="BLDG-2"))

    def test_scoped_supervisor_with_no_buildings_sees_nothing(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[]
        ):
            self.assertEqual(P._building_condition(user="sup"), "1=0")

    def test_oversight_role_is_unscoped(self):
        with patch.object(P, "_building_is_unscoped", return_value=True):
            self.assertEqual(P._building_condition(user="mgr"), "")
            self.assertIsNone(
                P.building_scoped_has_permission(
                    frappe._dict(doctype="Custody Issue", building="BLDG-2"),
                    "read",
                    user="mgr",
                )
            )

    def test_building_query_scopes_on_name_column(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=["BLDG-1"]
        ):
            self.assertIn("`name`", P.accommodation_building_query(user="sup"))


if __name__ == "__main__":
    unittest.main()
