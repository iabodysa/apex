# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests._helpers import _user
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


def _custody_assignment(building, assets, supervisor="Administrator", **overrides):
    fields = {
        "doctype": "Facility Asset Custody Assignment",
        "supervisor": supervisor,
        "building": building,
        "handover_date": today(),
        "all_assets_verified": 1,
        "assets_in_custody": [{"facility_asset": a.name} for a in assets],
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestFacilityAssetCustodyAssignmentSubmitGuards(FrappeTestCase):
    def test_submitting_without_any_assets_is_refused(self):
        building = make_building("_T-FACustody Empty Table")
        doc = _custody_assignment(building.name, [], all_assets_verified=1).insert(
            ignore_permissions=True
        )
        with self.assertRaises(frappe.ValidationError):
            doc.submit()

    def test_submitting_without_verifying_all_assets_is_refused(self):
        building = make_building("_T-FACustody Unverified")
        asset = _asset(building.name, "_T-FACustody-Asset-Unverified")
        doc = _custody_assignment(
            building.name, [asset], all_assets_verified=0
        ).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            doc.submit()


class TestFacilityAssetCustodyAssignmentSubmit(FrappeTestCase):
    def test_submitting_makes_the_supervisor_the_assets_custodian(self):
        building = make_building("_T-FACustody Assign")
        asset = _asset(building.name, "_T-FACustody-Asset-Assign")
        new_supervisor = _user("t-facustody-supervisor@example.com", "Accommodation Manager")
        doc = _custody_assignment(
            building.name, [asset], supervisor=new_supervisor
        ).insert(ignore_permissions=True)
        self.assertNotEqual(asset.responsible_supervisor, doc.supervisor)
        doc.submit()
        asset.reload()
        self.assertEqual(asset.responsible_supervisor, doc.supervisor)
