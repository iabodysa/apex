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


class TestAccommodationLedger(FrappeTestCase):

    def test_create_valid_ledger_entry(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Ledger",
            "posting_date": "2026-06-01",
            "building": "QA-BLDG",
            "ledger_type": "Rent",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
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

    @unittest.skip(
        "Frappe uses the first Select option as default for empty Select fields; "
        "ledger_type='Rent' is auto-applied so MandatoryError is never raised."
    )
    def test_missing_ledger_type_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Ledger",
            "posting_date": "2026-06-01",
            "building": "QA-BLDG",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
