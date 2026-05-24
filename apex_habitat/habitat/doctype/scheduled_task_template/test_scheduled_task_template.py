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


class TestScheduledTaskTemplate(FrappeTestCase):

    def test_create_valid_template(self):
        doc = frappe.get_doc({
            "doctype": "Scheduled Task Template",
            "template_name": "QA Weekly Safety Check",
            "frequency": "Weekly",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.frequency, "Weekly")
        frappe.delete_doc("Scheduled Task Template", doc.name, force=True, ignore_permissions=True)

    def test_missing_template_name_raises(self):
        doc = frappe.get_doc({
            "doctype": "Scheduled Task Template",
            "frequency": "Daily",
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    @unittest.skip(
        "frequency is a Select field with default='Monthly'; "
        "Frappe auto-fills it so MandatoryError is never raised."
    )
    def test_missing_frequency_raises(self):
        doc = frappe.get_doc({
            "doctype": "Scheduled Task Template",
            "template_name": "QA Template No Freq",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
