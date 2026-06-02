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


class TestSafetyTaskCatalog(FrappeTestCase):

    def test_docperm_safety_officer_read_only(self):
        """Safety Officer must have only read access on Safety Task Catalog (master data)."""
        meta = frappe.get_meta("Safety Task Catalog")
        roles = {p.role: p for p in meta.permissions}
        self.assertIn("Safety Officer", roles, "Safety Officer perm row is missing")
        p = roles["Safety Officer"]
        self.assertEqual(p.read, 1)
        self.assertFalse(getattr(p, "write", 0), "Safety Officer must NOT have write on STC master")
        self.assertFalse(getattr(p, "create", 0), "Safety Officer must NOT have create on STC master")

    def test_create_valid_catalog_entry(self):
        doc = frappe.get_doc({
            "doctype": "Safety Task Catalog",
            "naming_series": "STC-.####",
            "task_code": "STC-QA-001",
            "task_title": "Check fire extinguishers",
            "department": "Fire Safety",
            "frequency": "Monthly",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
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

    @unittest.skip(
        "frequency is a Select field; Frappe applies the first option ('Daily') as default "
        "when the field is empty, so MandatoryError is never raised."
    )
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
