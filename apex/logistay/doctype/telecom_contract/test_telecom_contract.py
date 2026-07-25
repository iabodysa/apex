# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests import factories

test_ignore = [
    "Company",
    "Supplier",
    "Currency",
    "Cost Center",
    "Project",
    "Item",
    "Employee",
    "Department",
]


class TestTelecomContract(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = factories.make_company("Test AFMCO").name

    def _contract(self, **kw):
        doc = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "naming_series": "TEL-CTR-.YYYY.-.#####",
                "company": self.company,
                "supplier": "QA-TELECOM-SUPPLIER",
                "contract_start_date": "2026-01-01",
                "contract_end_date": "2026-12-31",
                "billing_frequency": "Monthly",
                "recurring_amount": 100,
                "currency": "SAR",
                **kw,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        return doc

    def test_naming_series_applied(self):
        doc = self._contract()
        self.assertTrue(doc.name.startswith("TEL-CTR-"))
        frappe.delete_doc("Telecom Contract", doc.name, force=True, ignore_permissions=True)

    def test_end_before_start_raises(self):
        with self.assertRaises(frappe.ValidationError):
            self._contract(contract_start_date="2026-12-31", contract_end_date="2026-01-01")

    def test_status_draft_then_active_on_submit(self):
        doc = self._contract()
        self.assertEqual(doc.status, "Draft")
        doc.submit()
        self.assertEqual(doc.status, "Active")
        doc.cancel()
        self.assertEqual(frappe.db.get_value("Telecom Contract", doc.name, "status"), "Terminated")
        frappe.delete_doc("Telecom Contract", doc.name, force=True, ignore_permissions=True)

    def test_status_expired_when_period_past(self):
        doc = self._contract(contract_start_date="2020-01-01", contract_end_date="2020-12-31")
        doc.submit()
        self.assertEqual(doc.status, "Expired")
        doc.cancel()
        frappe.delete_doc("Telecom Contract", doc.name, force=True, ignore_permissions=True)

    def test_supplier_owns_multiple_contracts(self):
        first = self._contract()
        second = self._contract()
        self.assertNotEqual(first.name, second.name)
        self.assertEqual(first.supplier, second.supplier)
        for name in (first.name, second.name):
            frappe.delete_doc("Telecom Contract", name, force=True, ignore_permissions=True)
