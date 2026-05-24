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


class TestCustodyDamageItem(FrappeTestCase):

    def test_child_metadata(self):
        meta = frappe.get_meta("Custody Damage Item")
        self.assertEqual(meta.istable, 1)

    def test_row_in_memory(self):
        row = frappe.new_doc("Custody Damage Item")
        row.article = "test-art"
        row.damage_description = "broken"
        row.estimated_replacement_cost_sar = 100
        self.assertEqual(row.doctype, "Custody Damage Item")

    def test_required_fields_defined(self):
        meta = frappe.get_meta("Custody Damage Item")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("article", field_names)
        self.assertIn("damage_description", field_names)
        self.assertIn("estimated_replacement_cost_sar", field_names)
        self.assertTrue(len(field_names) > 0)
