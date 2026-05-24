import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestOperationalDepreciationPolicy(FrappeTestCase):

    def test_create_valid_policy(self):
        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Policy",
            "policy_name": "QA Straight Line Policy",
            "useful_life_years": 5,
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.useful_life_years, 5)
        frappe.delete_doc("Operational Depreciation Policy", doc.name, force=True, ignore_permissions=True)

    def test_missing_policy_name_raises(self):
        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Policy",
            "useful_life_years": 5,
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_useful_life_raises(self):
        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Policy",
            "policy_name": "QA Policy No Life",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
