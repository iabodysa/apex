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


class TestAccommodationCustodyItem(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Accommodation Custody Item")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Accommodation Custody Item")
        row.article = "test-article"
        row.quantity = 1
        self.assertEqual(row.doctype, "Accommodation Custody Item")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Accommodation Custody Item")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("article", field_names)
        self.assertIn("quantity", field_names)
        self.assertTrue(len(field_names) > 0)
