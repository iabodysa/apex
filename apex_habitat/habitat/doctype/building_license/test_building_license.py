import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestBuildingLicense(FrappeTestCase):

    def test_create_valid_license(self):
        doc = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "license_number": "LIC-QA-001",
            "issue_date": "2026-01-01",
            "expiry_date": "2027-01-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.license_number, "LIC-QA-001")
        frappe.delete_doc("Building License", doc.name, force=True, ignore_permissions=True)

    def test_missing_license_number_raises(self):
        doc = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "issue_date": "2026-01-01",
            "expiry_date": "2027-01-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_expiry_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Building License",
            "naming_series": "BLDG-LIC-.YYYY.-.####",
            "license_type": "Civil Defence Certificate",
            "building": "QA-BLDG",
            "license_number": "LIC-QA-002",
            "issue_date": "2026-01-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
