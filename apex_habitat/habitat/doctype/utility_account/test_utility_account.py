import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestUtilityAccount(FrappeTestCase):

    def test_create_valid_account(self):
        doc = frappe.get_doc({
            "doctype": "Utility Account",
            "naming_series": "UTIL-ACC-.####",
            "building": "QA-BLDG",
            "utility_type": "Electricity",
            "account_number": "ELEC-QA-00001",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.utility_type, "Electricity")
        frappe.delete_doc("Utility Account", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_raises(self):
        doc = frappe.get_doc({
            "doctype": "Utility Account",
            "utility_type": "Water",
            "account_number": "WAT-QA-00001",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_account_number_raises(self):
        doc = frappe.get_doc({
            "doctype": "Utility Account",
            "building": "QA-BLDG",
            "utility_type": "Gas",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
