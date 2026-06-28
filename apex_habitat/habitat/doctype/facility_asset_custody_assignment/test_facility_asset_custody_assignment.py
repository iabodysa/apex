# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

# [#8evoal]
test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]


class TestFacilityAssetCustodyAssignment(FrappeTestCase):

    def test_create_valid_custody_assignment(self):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Custody Assignment",
            "naming_series": "FAC-CUST-.YYYY.-.#####",
            "supervisor": "Administrator",
            "building": "QA-BLDG",
            "handover_date": "2026-06-01",
            "all_assets_verified": 1,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Facility Asset Custody Assignment", doc.name, force=True, ignore_permissions=True)

    def test_missing_supervisor_raises(self):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Custody Assignment",
            "naming_series": "FAC-CUST-.YYYY.-.#####",
            "building": "QA-BLDG",
            "handover_date": "2026-06-01",
            "all_assets_verified": 1,
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_handover_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Custody Assignment",
            "naming_series": "FAC-CUST-.YYYY.-.#####",
            "supervisor": "Administrator",
            "building": "QA-BLDG",
            "all_assets_verified": 1,
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def _make_asset(self, supervisor):
        asset = frappe.get_doc({
            "doctype": "Facility Asset",
            "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "QA Custody Camera",
            "asset_category": "CCTV Camera",
            "building": "QA-BLDG",
            "responsible_supervisor": supervisor,
        })
        asset.insert(ignore_permissions=True, ignore_links=True)
        return asset

    def _make_assignment(self, asset, supervisor):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Custody Assignment",
            "naming_series": "FAC-CUST-.YYYY.-.#####",
            "supervisor": supervisor,
            "building": "QA-BLDG",
            "handover_date": "2026-06-01",
            "all_assets_verified": 1,
            "assets_in_custody": [{"facility_asset": asset.name}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        doc.submit()
        return doc

    def test_submit_updates_asset_custodian(self):
        asset = self._make_asset("Administrator")
        doc = self._make_assignment(asset, "Guest")
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset.name, "responsible_supervisor"),
            "Guest",
        )
        doc.cancel()
        frappe.delete_doc("Facility Asset Custody Assignment", doc.name, force=True, ignore_permissions=True)
        frappe.delete_doc("Facility Asset", asset.name, force=True, ignore_permissions=True)

    def test_cancel_restores_prior_custodian(self):
        asset = self._make_asset("Administrator")
        first = self._make_assignment(asset, "Administrator")
        second = self._make_assignment(asset, "Guest")
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset.name, "responsible_supervisor"),
            "Guest",
        )
        second.cancel()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", asset.name, "responsible_supervisor"),
            "Administrator",
        )
        first.cancel()
        for name in (second.name, first.name):
            frappe.delete_doc("Facility Asset Custody Assignment", name, force=True, ignore_permissions=True)
        frappe.delete_doc("Facility Asset", asset.name, force=True, ignore_permissions=True)
