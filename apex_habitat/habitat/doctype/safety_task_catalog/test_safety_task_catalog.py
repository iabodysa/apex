import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestSafetyTaskCatalog(FrappeTestCase):

    def test_create_valid_catalog_entry(self):
        doc = frappe.get_doc({
            "doctype": "Safety Task Catalog",
            "naming_series": "STC-.####",
            "task_code": "STC-QA-001",
            "task_title": "Check fire extinguishers",
            "department": "Fire Safety",
            "frequency": "Monthly",
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.task_code, "STC-QA-001")
        frappe.delete_doc("Safety Task Catalog", doc.name, force=True, ignore_permissions=True)

    def test_missing_task_code_raises(self):
        doc = frappe.get_doc({
            "doctype": "Safety Task Catalog",
            "naming_series": "STC-.####",
            "task_title": "Inspect exits",
            "department": "Fire Safety",
            "frequency": "Daily",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_frequency_raises(self):
        doc = frappe.get_doc({
            "doctype": "Safety Task Catalog",
            "naming_series": "STC-.####",
            "task_code": "STC-QA-999",
            "task_title": "Inspect exits",
            "department": "Security",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
