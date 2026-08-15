# Copyright (c) 2026, AFMCO and contributors
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

from apex.habitat import permissions as P
from apex.habitat.report.building_operations_summary import (
    building_operations_summary as R,
)


class TestHousingSupervisorScope(FrappeTestCase):
    def test_scoped_supervisor_confined_to_his_buildings(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=["BLDG-1"]
        ):
            cond = P._building_condition(user="sup")
            self.assertIn("BLDG-1", cond)
            self.assertIn("`building`", cond)

            def hp(dt, **kw):
                return P.building_scoped_has_permission(
                    frappe._dict(doctype=dt, **kw), "read", user="sup"
                )

            self.assertIsNone(hp("Custody Issue", building="BLDG-1"))
            self.assertFalse(hp("Custody Issue", building="BLDG-2"))
            self.assertIsNone(hp("Housing Assignment", building="BLDG-1"))
            self.assertFalse(hp("Cleaning Log", building="BLDG-2"))
            self.assertIsNone(hp("Resident Request", building="BLDG-1"))
            self.assertFalse(hp("Resident Request", building="BLDG-2"))
            self.assertIsNone(hp("Idle Resident Report", building="BLDG-1"))
            self.assertFalse(hp("Idle Resident Report", building="BLDG-2"))
            self.assertFalse(hp("Cleaning Log", building=None))
            self.assertIsNone(hp("Building", name="BLDG-1"))
            self.assertFalse(hp("Building", name="BLDG-2"))

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
            self.assertIn("`name`", P.building_scope_query(user="sup", doctype="Building"))

    def test_resident_request_and_idle_report_scope_on_building_column(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=["BLDG-1"]
        ):
            for doctype in ("Resident Request", "Idle Resident Report"):
                cond = P.building_scope_query(user="sup", doctype=doctype)
                self.assertIn("`building`", cond)
                self.assertIn("BLDG-1", cond)

    def test_report_scoped_supervisor_only_queries_his_buildings(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=["BLDG-1", "BLDG-2"]
        ), patch.object(R.frappe, "get_all", return_value=[]) as ga:
            R._get_buildings(None)
            ga.assert_called_once()
            self.assertEqual(ga.call_args.kwargs["filters"]["name"], ["in", ["BLDG-1", "BLDG-2"]])

    def test_report_explicit_filter_intersected_with_scope(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=["BLDG-1"]
        ), patch.object(R.frappe, "get_all", return_value=[]) as ga:
            R._get_buildings("BLDG-1")
            self.assertEqual(ga.call_args.kwargs["filters"]["name"], ["in", ["BLDG-1"]])
            self.assertEqual(R._get_buildings("BLDG-9"), [])

    def test_report_scoped_supervisor_with_no_buildings_queries_nothing(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[]
        ), patch.object(R.frappe, "get_all", return_value=[]) as ga:
            self.assertEqual(R._get_buildings(None), [])
            ga.assert_not_called()

    def test_report_unscoped_role_sees_all_active(self):
        with patch.object(P, "_building_is_unscoped", return_value=True), patch.object(
            R.frappe, "get_all", return_value=[]
        ) as ga:
            R._get_buildings(None)
            self.assertEqual(ga.call_args.kwargs["filters"], {"status": "Active"})

    def test_report_scope_gap_returns_guidance_message(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[]
        ):
            res = R.execute({})
            self.assertEqual(len(res), 3)
            columns, data, message = res
            self.assertEqual(data, [])
            self.assertTrue(columns)
            self.assertTrue(message)

    def test_report_empty_estate_has_no_scope_message(self):
        with patch.object(P, "_building_is_unscoped", return_value=True), patch.object(
            R.frappe, "get_all", return_value=[]
        ):
            res = R.execute({})
            self.assertEqual(len(res), 2)
            self.assertEqual(res[1], [])

    def test_report_out_of_scope_filter_is_not_a_gap(self):
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=["BLDG-1"]
        ):
            res = R.execute({"building": "BLDG-9"})
            self.assertEqual(len(res), 2)
            self.assertEqual(res[1], [])


if __name__ == "__main__":
    unittest.main()
