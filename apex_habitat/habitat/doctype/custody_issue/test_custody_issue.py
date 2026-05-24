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


class TestCustodyIssue(FrappeTestCase):

    def test_create_valid_issue(self):
        doc = frappe.get_doc({
            "doctype": "Custody Issue",
            "naming_series": "CUST-ISS-.YYYY.-.####",
            "issue_date": "2026-06-01",
            "building": "QA-BLDG",
            "items": [{"doctype": "Custody Issue Item", "article": "QA-ART", "qty": 1}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Custody Issue", doc.name, force=True, ignore_permissions=True)

    def test_missing_issue_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Custody Issue",
            "naming_series": "CUST-ISS-.YYYY.-.####",
            "building": "QA-BLDG",
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_empty_items_raises(self):
        from apex_habitat.habitat.doctype.custody_issue.custody_issue import validate

        doc = frappe.get_doc({
            "doctype": "Custody Issue",
            "issue_date": "2026-06-01",
            "building": "QA-BLDG",
            "items": [],
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)
