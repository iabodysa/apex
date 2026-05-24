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


class TestAccommodationBed(FrappeTestCase):

    def test_create_valid_bed(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Bed",
            "naming_series": "BED-.####",
            "room": "ROOM-0001",
            "bed_code": "B-A1",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.bed_code, "B-A1")
        frappe.delete_doc("Accommodation Bed", doc.name, force=True, ignore_permissions=True)

    def test_missing_room_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Bed",
            "naming_series": "BED-.####",
            "bed_code": "B-X9",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_bed_code_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Bed",
            "naming_series": "BED-.####",
            "room": "ROOM-0001",
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)
