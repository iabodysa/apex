import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestAccommodationLedger(FrappeTestCase):

    def test_create_valid_ledger_entry(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Ledger",
            "posting_date": "2026-06-01",
            "building": "QA-BLDG",
            "ledger_type": "Rent",
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.ledger_type, "Rent")
        frappe.delete_doc("Accommodation Ledger", doc.name, force=True, ignore_permissions=True)

    def test_missing_posting_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Ledger",
            "building": "QA-BLDG",
            "ledger_type": "Electricity",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_ledger_type_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Ledger",
            "posting_date": "2026-06-01",
            "building": "QA-BLDG",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
