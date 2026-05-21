import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestRoomBedTransfer(FrappeTestCase):

    def test_create_valid_transfer(self):
        doc = frappe.get_doc({
            "doctype": "Room Bed Transfer",
            "naming_series": "RBT-.YYYY.-.####",
            "assignment": "ACC-ASGN-QA",
            "to_room": "ROOM-QA",
            "to_bed": "BED-QA",
            "transfer_date": "2026-06-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Room Bed Transfer", doc.name, force=True, ignore_permissions=True)

    def test_missing_assignment_raises(self):
        doc = frappe.get_doc({
            "doctype": "Room Bed Transfer",
            "naming_series": "RBT-.YYYY.-.####",
            "to_room": "ROOM-QA",
            "to_bed": "BED-QA",
            "transfer_date": "2026-06-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_transfer_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Room Bed Transfer",
            "naming_series": "RBT-.YYYY.-.####",
            "assignment": "ACC-ASGN-QA",
            "to_room": "ROOM-QA",
            "to_bed": "BED-QA",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
