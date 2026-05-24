import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestCleaningLog(FrappeTestCase):

    def test_create_valid_cleaning_log(self):
        doc = frappe.get_doc({
            "doctype": "Cleaning Log",
            "naming_series": "CLEAN-.YYYY.-.####",
            "building": "QA-BLDG",
            "cleaning_date": "2026-06-15",
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.cleaning_date, "2026-06-15")
        frappe.delete_doc("Cleaning Log", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_raises(self):
        doc = frappe.get_doc({
            "doctype": "Cleaning Log",
            "naming_series": "CLEAN-.YYYY.-.####",
            "cleaning_date": "2026-06-15",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_cleaning_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Cleaning Log",
            "naming_series": "CLEAN-.YYYY.-.####",
            "building": "QA-BLDG",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
