import frappe
from frappe.tests.utils import FrappeTestCase


class TestSafetyInspectionReport(FrappeTestCase):

    def test_create_valid_inspection(self):
        doc = frappe.get_doc({
            "doctype": "Safety Inspection Report",
            "naming_series": "FSI-.YYYY.-.#####",
            "building": "QA-BLDG",
            "inspection_date": "2026-06-15",
            "inspector": "Administrator",
        })
        doc.insert(ignore_permissions=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Safety Inspection Report", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_raises(self):
        doc = frappe.get_doc({
            "doctype": "Safety Inspection Report",
            "naming_series": "FSI-.YYYY.-.#####",
            "inspection_date": "2026-06-15",
            "inspector": "Administrator",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_inspector_raises(self):
        doc = frappe.get_doc({
            "doctype": "Safety Inspection Report",
            "naming_series": "FSI-.YYYY.-.#####",
            "building": "QA-BLDG",
            "inspection_date": "2026-06-15",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
