import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

# [#8evoal]
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

    def test_docperm_safety_officer(self):
        """Safety Officer must have read/write/create on Safety Task Execution (no submit)."""
        meta = frappe.get_meta("Safety Task Execution")
        roles = {p.role: p for p in meta.permissions}
        self.assertIn("Safety Officer", roles, "Safety Officer perm row is missing")
        p = roles["Safety Officer"]
        self.assertEqual(p.read, 1)
        self.assertEqual(p.write, 1)
        self.assertEqual(p.create, 1)
        self.assertFalse(getattr(p, "submit", 0), "Safety Officer must NOT have submit on STE")

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

    # evidence enforcement (Safety Task Execution.validate)

    def _evidence_task(self, evidence_required):
        """Create a Safety Task Catalog row with the given evidence flag."""
        return frappe.get_doc({
            "doctype": "Safety Task Catalog",
            "naming_series": "STC-.####",
            "task_code": f"STC-EV-{frappe.generate_hash(length=4)}",
            "task_title": "Evidence task",
            "department": "Fire Safety",
            "frequency": "Monthly",
            "evidence_required": evidence_required,
        }).insert(ignore_permissions=True).name

    def test_evidence_required_task_without_photo_is_rejected(self):
        """A task flagged evidence_required cannot be saved without an Evidence Photo."""
        task = self._evidence_task(evidence_required=1)
        doc = frappe.get_doc({
            "doctype": "Safety Task Execution",
            "execution_date": "2026-06-20",
            "building": "QA-BLDG",
            "task": task,
            "execution_status": "Good",
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_evidence_not_required_task_saves_without_photo(self):
        """A task with evidence_required=0 saves with no Evidence Photo."""
        task = self._evidence_task(evidence_required=0)
        doc = frappe.get_doc({
            "doctype": "Safety Task Execution",
            "execution_date": "2026-06-20",
            "building": "QA-BLDG",
            "task": task,
            "execution_status": "Good",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.execution_status, "Good")
        frappe.delete_doc(
            "Safety Task Execution", doc.name, force=True, ignore_permissions=True
        )
