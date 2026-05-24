import frappe
from frappe.tests.utils import FrappeTestCase


class TestUtilityBillEntry(FrappeTestCase):

    def test_create_valid_bill(self):
        doc = frappe.get_doc({
            "doctype": "Utility Bill Entry",
            "naming_series": "UTIL-BILL-.YYYY.-.#####",
            "utility_account": "UTIL-ACC-QA",
            "billing_period_from": "2026-06-01",
            "billing_period_to": "2026-06-30",
            "bill_amount_sar": 1200,
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.bill_amount_sar, 1200)
        frappe.delete_doc("Utility Bill Entry", doc.name, force=True, ignore_permissions=True)

    def test_missing_utility_account_raises(self):
        doc = frappe.get_doc({
            "doctype": "Utility Bill Entry",
            "naming_series": "UTIL-BILL-.YYYY.-.#####",
            "billing_period_from": "2026-06-01",
            "billing_period_to": "2026-06-30",
            "bill_amount_sar": 900,
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_period_to_before_from_raises(self):
        from apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry import validate
        doc = frappe.get_doc({
            "doctype": "Utility Bill Entry",
            "utility_account": "UTIL-ACC-QA",
            "billing_period_from": "2026-06-30",
            "billing_period_to": "2026-06-01",
            "bill_amount_sar": 500,
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)
