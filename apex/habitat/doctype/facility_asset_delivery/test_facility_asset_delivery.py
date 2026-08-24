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


def _delivery(asset, to_building, **overrides):
    fields = {
        "doctype": "Facility Asset Delivery",
        "delivery_date": today(),
        "facility_asset": asset.name,
        "to_building": to_building,
        "initiated_by": "Administrator",
        "receiving_supervisor": _user("t-fadelivery-receiver@example.com", "Accommodation Manager"),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestFacilityAssetDeliveryBuildings(FrappeTestCase):
    def test_source_and_destination_buildings_must_differ(self):
        building = make_building("_T-FADelivery Same Building")
        asset = _asset(building.name, "_T-FADelivery-Asset-Same")
        doc = _delivery(asset, building.name)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)


class TestFacilityAssetDeliveryPeople(FrappeTestCase):
    def test_initiator_and_receiving_supervisor_must_differ(self):
        source = make_building("_T-FADelivery People Source")
        dest = make_building("_T-FADelivery People Dest")
        asset = _asset(source.name, "_T-FADelivery-Asset-People")
        doc = _delivery(
            asset, dest.name, initiated_by="Administrator", receiving_supervisor="Administrator"
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)


class TestFacilityAssetDeliverySubmit(FrappeTestCase):
    def test_submitting_sets_status_to_pending_exits(self):
        source = make_building("_T-FADelivery Submit Source")
        dest = make_building("_T-FADelivery Submit Dest")
        asset = _asset(source.name, "_T-FADelivery-Asset-Submit")
        doc = _delivery(asset, dest.name).insert(ignore_permissions=True)
        doc.submit()
        self.assertEqual(doc.status, "Pending Exits")


class TestFacilityAssetDeliveryCancel(FrappeTestCase):
    def test_cancelling_without_a_reason_is_refused(self):
        source = make_building("_T-FADelivery Cancel Source")
        dest = make_building("_T-FADelivery Cancel Dest")
        asset = _asset(source.name, "_T-FADelivery-Asset-Cancel")
        doc = _delivery(asset, dest.name).insert(ignore_permissions=True)
        doc.submit()
        with self.assertRaises(frappe.ValidationError):
            doc.cancel()
