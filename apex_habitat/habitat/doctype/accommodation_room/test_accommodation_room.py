import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


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

    def test_missing_bed_capacity_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Room",
            "naming_series": "ROOM-.####",
            "building": "QA-BLDG",
            "room_number": "R888",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
