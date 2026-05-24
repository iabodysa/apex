import frappe
from frappe.tests.utils import FrappeTestCase


class TestMaintenanceRequest(FrappeTestCase):

    def test_create_valid_request(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "room": "ROOM-QA",
            "reported_by": "Administrator",
            "issue_type": "Plumbing",
            "issue_description": "Leak under sink",
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.issue_type, "Plumbing")
        frappe.delete_doc("Maintenance Request", doc.name, force=True, ignore_permissions=True)

    def test_missing_room_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "reported_by": "Administrator",
            "issue_type": "Electrical",
            "issue_description": "Wiring problem",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_issue_description_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "room": "ROOM-QA",
            "reported_by": "Administrator",
            "issue_type": "Plumbing",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
