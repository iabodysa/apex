# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests.factories import make_building

test_ignore = ["Facility Asset"]


def _asset(building, name):
    return frappe.get_doc(
        {
            "doctype": "Facility Asset",
            "asset_name": name,
            "asset_category": "Other",
            "building": building,
            "responsible_supervisor": "Administrator",
        }
    ).insert(ignore_permissions=True)


def _movement(asset, to_building, **overrides):
    fields = {
        "doctype": "Facility Asset Movement",
        "movement_date": today(),
        "facility_asset": asset.name,
        "movement_category": "Same-Company Relocation",
        "to_building": to_building,
        "release_approved_by": "Administrator",
        "receiving_confirmed_by": "test@example.com",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestFacilityAssetMovementLocationChange(FrappeTestCase):
    def test_a_movement_to_the_assets_own_location_is_refused(self):
        building = make_building("_T-FAMovement Same Location")
        asset = _asset(building.name, "_T-FAMovement-Asset-Same")
        doc = _movement(asset, building.name)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)


class TestFacilityAssetMovementIntercompanyGates(FrappeTestCase):
    def test_an_intercompany_movement_without_release_approval_is_refused(self):
        source = make_building("_T-FAMovement IC Source")
        dest = make_building("_T-FAMovement IC Dest")
        company_b = frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": "_T-FAMovement Company B",
                "abbr": "TFCB",
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        )
        if not frappe.db.exists("Company", company_b.company_name):
            company_b.insert(ignore_permissions=True)
        frappe.db.set_value("Building", dest.name, "company", "_T-FAMovement Company B")
        asset = _asset(source.name, "_T-FAMovement-Asset-IC")
        doc = _movement(asset, dest.name, release_approved_by=None)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)


class TestFacilityAssetMovementSubmit(FrappeTestCase):
    def test_submitting_relocates_the_asset_and_increments_its_movement_count(self):
        source = make_building("_T-FAMovement Submit Source")
        dest = make_building("_T-FAMovement Submit Dest")
        asset = _asset(source.name, "_T-FAMovement-Asset-Submit")
        doc = _movement(asset, dest.name).insert(ignore_permissions=True)
        doc.submit()
        asset.reload()
        self.assertEqual(asset.building, dest.name)
        self.assertEqual(asset.movement_count, 1)


class TestFacilityAssetMovementCancel(FrappeTestCase):
    def test_cancelling_without_a_reason_is_refused(self):
        source = make_building("_T-FAMovement Cancel Source")
        dest = make_building("_T-FAMovement Cancel Dest")
        asset = _asset(source.name, "_T-FAMovement-Asset-Cancel")
        doc = _movement(asset, dest.name).insert(ignore_permissions=True)
        doc.submit()
        with self.assertRaises(frappe.ValidationError):
            doc.cancel()
