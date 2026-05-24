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


class TestCustodyAssetCategory(FrappeTestCase):

    def test_create_valid_category(self):
        doc = frappe.get_doc({
            "doctype": "Custody Asset Category",
            "category_name": "QA Bedding",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.category_name, "QA Bedding")
        frappe.delete_doc("Custody Asset Category", doc.name, force=True, ignore_permissions=True)

    def test_missing_category_name_raises(self):
        doc = frappe.get_doc({
            "doctype": "Custody Asset Category",
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_duplicate_category_name_raises(self):
        doc1 = frappe.get_doc({"doctype": "Custody Asset Category", "category_name": "QA Dup Cat"})
        doc1.insert(ignore_permissions=True, ignore_links=True)
        doc2 = frappe.get_doc({"doctype": "Custody Asset Category", "category_name": "QA Dup Cat"})
        with self.assertRaises(Exception):
            doc2.insert(ignore_permissions=True, ignore_links=True)
        frappe.delete_doc("Custody Asset Category", doc1.name, force=True, ignore_permissions=True)
