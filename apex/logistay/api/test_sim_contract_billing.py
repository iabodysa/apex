# Copyright (c) 2026, AFMCO and contributors
"""Contract billing actions: a submitted Telecom Contract yields one draft purchase
request (Material Request) per billing period, mapped correctly, deduplicated, and
never submitted.

The payment half lives in ``test_telecom_payment_allocation.py``: a payment needs a
Purchase Invoice to allocate against, so its fixtures are finance fixtures and do
not belong next to the procurement ones."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.logistay.api import contract_billing
from apex.tests import factories

test_ignore = ["Company", "Supplier", "Currency", "Cost Center", "Project", "Item"]


service_item = factories.service_item


class TestSIMContractBilling(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = factories.make_company("Test AFMCO").name
        cls.supplier = cls._supplier("QA Telecom Operator")
        cls.item = service_item("QA Telecom Service")
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

    def test_no_action_here_raises_a_payment_on_its_own(self):
        """The retired ``create_payment_order`` created an UNALLOCATED Payment Entry
        from the contract alone — no invoice, no reference, nothing settled. It is
        gone, and the procurement action must not have grown a payment side door."""
        self.assertFalse(hasattr(contract_billing, "create_payment_order"))
        contract = self._contract()
        before = frappe.db.count("Payment Entry", {"party_type": "Supplier", "party": self.supplier})
        contract_billing.create_purchase_request(contract.name, "2026-07")
        self.assertEqual(
            frappe.db.count("Payment Entry", {"party_type": "Supplier", "party": self.supplier}),
            before,
        )

    def test_actions_require_submitted_contract(self):
        draft = self._contract(submit=False)
        with self.assertRaises(frappe.ValidationError):
            contract_billing.create_purchase_request(draft.name, "2026-07")

    def test_invalid_period_rejected(self):
        contract = self._contract()
        with self.assertRaises(frappe.ValidationError):
            contract_billing.create_purchase_request(contract.name, "July-2026")
