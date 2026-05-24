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


class TestAccommodationCheckout(FrappeTestCase):

    def test_create_valid_checkout(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Checkout",
            "naming_series": "ACC-CHKOUT-.YYYY.-.####",
            "assignment": "ACC-ASGN-QA",
            "checkout_date": "2026-07-01",
            "checkout_reason": "End of Contract",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.checkout_reason, "End of Contract")
        frappe.delete_doc("Accommodation Checkout", doc.name, force=True, ignore_permissions=True)

    def test_missing_assignment_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Checkout",
            "naming_series": "ACC-CHKOUT-.YYYY.-.####",
            "checkout_date": "2026-07-01",
            "checkout_reason": "Final Exit",
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_checkout_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Checkout",
            "naming_series": "ACC-CHKOUT-.YYYY.-.####",
            "assignment": "ACC-ASGN-QA",
            "checkout_reason": "Final Exit",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
