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


class TestCameraAccessGrant(FrappeTestCase):

    def test_create_valid_grant(self):
        doc = frappe.get_doc({
            "doctype": "Camera Access Grant",
            "naming_series": "CAM-ACC-.YYYY.-.####",
            "requested_for": "Administrator",
            "valid_from": "2026-06-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Camera Access Grant", doc.name, force=True, ignore_permissions=True)

    def test_missing_requested_for_raises(self):
        doc = frappe.get_doc({
            "doctype": "Camera Access Grant",
            "naming_series": "CAM-ACC-.YYYY.-.####",
            "valid_from": "2026-06-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_valid_from_raises(self):
        doc = frappe.get_doc({
            "doctype": "Camera Access Grant",
            "naming_series": "CAM-ACC-.YYYY.-.####",
            "requested_for": "Administrator",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
