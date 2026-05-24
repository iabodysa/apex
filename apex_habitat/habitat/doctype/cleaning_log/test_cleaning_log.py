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


class TestCleaningLog(FrappeTestCase):

    def test_create_valid_cleaning_log(self):
        doc = frappe.get_doc({
            "doctype": "Cleaning Log",
            "naming_series": "CLEAN-.YYYY.-.####",
            "building": "QA-BLDG",
            "cleaning_date": "2026-06-15",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
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
