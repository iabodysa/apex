import frappe
from frappe.tests.utils import FrappeTestCase


class TestSubcontractorServiceOrder(FrappeTestCase):

    def test_create_valid_order(self):
        doc = frappe.get_doc({
            "doctype": "Subcontractor Service Order",
            "naming_series": "SSO-.YYYY.-.#####",
            "contract": "SUB-CON-QA",
            "building": "QA-BLDG",
            "scheduled_date": "2026-07-05",
        })
        doc.insert(ignore_permissions=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Subcontractor Service Order", doc.name, force=True, ignore_permissions=True)

    def test_missing_contract_raises(self):
        doc = frappe.get_doc({
            "doctype": "Subcontractor Service Order",
            "naming_series": "SSO-.YYYY.-.#####",
            "building": "QA-BLDG",
            "scheduled_date": "2026-07-05",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_scheduled_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Subcontractor Service Order",
            "naming_series": "SSO-.YYYY.-.#####",
            "contract": "SUB-CON-QA",
            "building": "QA-BLDG",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
