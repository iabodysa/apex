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


class TestAuditRemediationItem(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Audit Remediation Item")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Audit Remediation Item")
        row.finding_description = "desc"
        row.remediation_action = "action"
        row.due_date = "2026-06-01"
        self.assertEqual(row.doctype, "Audit Remediation Item")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Audit Remediation Item")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("finding_description", field_names)
        self.assertIn("remediation_action", field_names)
        self.assertIn("due_date", field_names)
        self.assertTrue(len(field_names) > 0)
