# Copyright (c) 2026, afmcoltd
"""Facility Asset's own contract: it needs a name and a building, and it takes the name it is given.

The building comes from ``test_records.json``, so the link is really checked, rather than a
``QA-BLDG`` name that exists on no site with ``ignore_links=True`` passed to stop Frappe noticing,
or a sixteen-line ``test_ignore`` block for masters the asset does not link to.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]

# `linked_erpnext_asset` is the bridge to ERPNext Asset and no test record sets it, but
# `get_dependencies` (frappe/test_runner.py:358-380) walks every Link field regardless. Walking
# Asset drags in ERPNext's purchase chain, which ends at `Payment Gateway` — a DocType that ships
# with the separate `payments` app and is absent from a frappe/erpnext/hrms bench, so the walk
# raises DoesNotExistError before a single Facility Asset is created.
test_ignore = ["Asset"]

BUILDING = "_Test Building"


class TestFacilityAsset(FrappeTestCase):
    def _asset(self, **overrides):
        payload = {
            "doctype": "Facility Asset",
            "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "_T CCTV Camera 1",
            "asset_category": "CCTV Camera",
            "building": BUILDING,
            "responsible_supervisor": "Administrator",
        }
        payload.update(overrides)
        return frappe.get_doc(payload)

    def test_an_asset_takes_the_name_it_is_given(self):
        asset = self._asset()
        asset.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Facility Asset", asset.name, force=True, ignore_permissions=True
        )

        self.assertEqual(asset.asset_name, "_T CCTV Camera 1")
        self.assertEqual(asset.building, BUILDING)

    def test_an_asset_without_a_name_is_refused(self):
        asset = self._asset(asset_name=None)

        with self.assertRaises(frappe.exceptions.MandatoryError):
            asset.insert(ignore_permissions=True)

    def test_an_asset_without_a_building_is_refused(self):
        asset = self._asset(asset_name="_T Generator", asset_category="Generator", building=None)

        with self.assertRaises(frappe.exceptions.MandatoryError):
            asset.insert(ignore_permissions=True)
