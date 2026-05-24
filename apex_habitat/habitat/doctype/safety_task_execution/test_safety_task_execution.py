import frappe
from frappe.tests.utils import FrappeTestCase


class TestSafetyTaskExecution(FrappeTestCase):

    def test_create_valid_execution(self):
        doc = frappe.get_doc({
            "doctype": "Safety Task Execution",
            "naming_series": "STE-.YYYY.-.#####",
            "execution_date": "2026-06-20",
            "building": "QA-BLDG",
            "task": "STC-QA-001",
            "execution_status": "Good",
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.execution_status, "Good")
        frappe.delete_doc("Safety Task Execution", doc.name, force=True, ignore_permissions=True)

    def test_missing_execution_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Safety Task Execution",
            "naming_series": "STE-.YYYY.-.#####",
            "building": "QA-BLDG",
            "task": "STC-QA-001",
            "execution_status": "Good",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_execution_status_raises(self):
        doc = frappe.get_doc({
            "doctype": "Safety Task Execution",
            "naming_series": "STE-.YYYY.-.#####",
            "execution_date": "2026-06-20",
            "building": "QA-BLDG",
            "task": "STC-QA-001",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
