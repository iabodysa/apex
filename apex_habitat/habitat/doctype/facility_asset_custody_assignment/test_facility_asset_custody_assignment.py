import frappe
from frappe.tests.utils import FrappeTestCase


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
        doc.insert(ignore_permissions=True)
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
