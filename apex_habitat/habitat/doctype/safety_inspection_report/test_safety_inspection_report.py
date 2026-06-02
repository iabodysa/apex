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


class TestSafetyInspectionReport(FrappeTestCase):

    def test_docperm_safety_officer(self):
        """Safety Officer must have read/write/create on Safety Inspection Report (no submit)."""
        meta = frappe.get_meta("Safety Inspection Report")
        roles = {p.role: p for p in meta.permissions}
        self.assertIn("Safety Officer", roles, "Safety Officer perm row is missing")
        p = roles["Safety Officer"]
        self.assertEqual(p.read, 1)
        self.assertEqual(p.write, 1)
        self.assertEqual(p.create, 1)
        self.assertFalse(getattr(p, "submit", 0), "Safety Officer must NOT have submit on SIR")

    def test_create_valid_inspection(self):
        doc = frappe.get_doc({
            "doctype": "Safety Inspection Report",
            "naming_series": "FSI-.YYYY.-.#####",
            "building": "QA-BLDG",
            "inspection_date": "2026-06-15",
            "inspector": "Administrator",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Safety Inspection Report", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_raises(self):
        doc = frappe.get_doc({
            "doctype": "Safety Inspection Report",
            "naming_series": "FSI-.YYYY.-.#####",
            "inspection_date": "2026-06-15",
            "inspector": "Administrator",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_inspector_raises(self):
        doc = frappe.get_doc({
            "doctype": "Safety Inspection Report",
            "naming_series": "FSI-.YYYY.-.#####",
            "building": "QA-BLDG",
            "inspection_date": "2026-06-15",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
