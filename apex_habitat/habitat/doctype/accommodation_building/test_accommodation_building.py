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


class TestAccommodationBuilding(FrappeTestCase):

    def test_create_valid_building(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": "QA Test Building",
            "total_capacity": 20,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.building_name, "QA Test Building")
        frappe.delete_doc("Accommodation Building", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_name_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Building",
            "total_capacity": 10,
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_capacity_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": "QA Missing Capacity",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
