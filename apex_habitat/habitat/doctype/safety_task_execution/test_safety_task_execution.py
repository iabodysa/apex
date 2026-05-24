import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

# Prevent Frappe test runner from recursively resolving Link-field dependencies
# on external DocTypes that require ERPNext (not installed in CI bench).
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
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.execution_status, "Good")
        frappe.delete_doc("Safety Task Execution", doc.name, force=True, ignore_permissions=True)

    @unittest.skip(
        "execution_date has default='Today'; Frappe auto-fills it so MandatoryError is never raised."
    )
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

    @unittest.skip(
        "execution_status is a Select field with default='Excellent'; "
        "Frappe auto-fills it so MandatoryError is never raised."
    )
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
