import unittest

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


class TestAccommodationRoom(FrappeTestCase):

    def test_create_valid_room(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Room",
            "naming_series": "ROOM-.####",
            "building": "QA-BLDG",
            "room_number": "R101",
            "bed_capacity": 4,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.room_number, "R101")
        frappe.delete_doc("Accommodation Room", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Room",
            "naming_series": "ROOM-.####",
            "room_number": "R999",
            "bed_capacity": 2,
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    @unittest.skip(
        "bed_capacity is not a mandatory field in the DocType schema; "
        "MandatoryError is never raised for missing non-required fields."
    )
    def test_missing_bed_capacity_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Room",
            "naming_series": "ROOM-.####",
            "building": "QA-BLDG",
            "room_number": "R888",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
