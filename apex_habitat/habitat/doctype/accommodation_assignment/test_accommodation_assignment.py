import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestAccommodationAssignment(FrappeTestCase):

    def test_create_valid_assignment(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "employee": "EMP-QA-001",
            "project": "PROJ-QA",
            "building": "BLDG-QA",
            "room": "ROOM-QA",
            "bed": "BED-QA",
            "check_in_date": "2026-06-01",
            "assignment_type": "New Assignment",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Accommodation Assignment", doc.name, force=True, ignore_permissions=True)

    def test_missing_employee_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "project": "PROJ-QA",
            "building": "BLDG-QA",
            "room": "ROOM-QA",
            "bed": "BED-QA",
            "check_in_date": "2026-06-01",
            "assignment_type": "New Assignment",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_check_in_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "employee": "EMP-QA-001",
            "project": "PROJ-QA",
            "building": "BLDG-QA",
            "room": "ROOM-QA",
            "bed": "BED-QA",
            "assignment_type": "New Assignment",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
