# Copyright (c) 2026, AFMCO and contributors
"""Contract billing actions: a submitted Telecom Contract yields one draft
purchase request (Material Request) and one draft payment order (Payment Entry)
per billing period, mapped correctly, deduplicated, and never submitted."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.sim_operations.api import contract_billing
from apex.tests import factories

test_ignore = ["Company", "Supplier", "Currency", "Cost Center", "Project", "Item"]


class TestSIMContractBilling(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = factories.make_company("Test AFMCO").name
        cls.supplier = cls._supplier("QA Telecom Operator")
        cls.item = cls._service_item("QA Telecom Service")
        # Ensure a default cash account so the payment-order path resolves.
        cash = frappe.db.get_value(
            "Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
        )
        if cash:
            frappe.db.set_value("Company", cls.company, "default_cash_account", cash)

    @staticmethod
    def _supplier(name):
        if not frappe.db.exists("Supplier", name):
            frappe.get_doc(
                {"doctype": "Supplier", "supplier_name": name, "supplier_group": "All Supplier Groups"}
            ).insert(ignore_permissions=True)
        return name

    @staticmethod
    def _service_item(name):
        if frappe.db.exists("Item", name):
            return name
        group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": name,
                "item_name": name,
                "item_group": group,
                "stock_uom": "Nos",
                "is_stock_item": 0,
            }
        ).insert(ignore_permissions=True)
        return name

    def _contract(self, with_item=True, submit=True):
        doc = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "naming_series": "TEL-CTR-.YYYY.-.#####",
                "company": self.company,
                "supplier": self.supplier,
                "contract_start_date": "2026-01-01",
                "contract_end_date": "2026-12-31",
                "billing_frequency": "Monthly",
                "recurring_amount": 250,
                "currency": "SAR",
                "service_item": self.item if with_item else None,
            }
        )
        doc.insert(ignore_permissions=True)
        if submit:
            doc.submit()
        return doc

    def setUp(self):
        # Per-test savepoint: roll back only this test's writes, keeping the class
        # fixtures (company/supplier/item) created in setUpClass alive so every test
        # can insert a contract that links to them.
        frappe.db.savepoint("sim_billing_test")

    def tearDown(self):
        frappe.db.rollback(save_point="sim_billing_test")

    def test_purchase_request_created_mapped_and_deduped(self):
        contract = self._contract()
        first = contract_billing.create_purchase_request(contract.name, "2026-07")
        self.assertFalse(first["existing"])
        mr = frappe.get_doc("Material Request", first["document_name"])
        self.assertEqual(mr.docstatus, 0)
        self.assertEqual(mr.company, self.company)
        self.assertEqual(mr.material_request_type, "Purchase")
        self.assertEqual(mr.items[0].item_code, self.item)
        # Second call for the same period returns the same draft.
        again = contract_billing.create_purchase_request(contract.name, "2026-07")
        self.assertTrue(again["existing"])
        self.assertEqual(again["document_name"], first["document_name"])

    def test_purchase_request_requires_service_item(self):
        contract = self._contract(with_item=False)
        with self.assertRaises(frappe.ValidationError):
            contract_billing.create_purchase_request(contract.name, "2026-07")

    def test_payment_order_draft_only_no_submit(self):
        contract = self._contract()
        result = contract_billing.create_payment_order(contract.name, "2026-07")
        pe = frappe.get_doc("Payment Entry", result["document_name"])
        self.assertEqual(pe.docstatus, 0)
        self.assertEqual(pe.payment_type, "Pay")
        self.assertEqual(pe.party, self.supplier)
        self.assertEqual(pe.paid_amount, 250)
        # Duplicate call returns the same draft.
        again = contract_billing.create_payment_order(contract.name, "2026-07")
        self.assertEqual(again["document_name"], result["document_name"])

    def test_actions_require_submitted_contract(self):
        draft = self._contract(submit=False)
        with self.assertRaises(frappe.ValidationError):
            contract_billing.create_purchase_request(draft.name, "2026-07")

    def test_invalid_period_rejected(self):
        contract = self._contract()
        with self.assertRaises(frappe.ValidationError):
            contract_billing.create_purchase_request(contract.name, "July-2026")
