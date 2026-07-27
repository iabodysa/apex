# Copyright (c) 2026, AFMCO and contributors
"""A telecom payment must settle a real payable, not sit on account.

A Payment Entry with no ``references`` row is an ON-ACCOUNT payment: it moves money
against the supplier's payable in aggregate and closes no invoice, so no
``outstanding_amount`` changes and nothing reconciles. Calling that "the telecom
bill is paid" is a claim the ledger does not support, and it is what this module
holds shut.

The mechanism under test is native: ERPNext's ``get_payment_entry`` builds the
Payment Entry FROM a Purchase Invoice and fills the ``references`` table itself
(payment_entry.py:3008). The tests therefore check the ALLOCATION, not the amount —
an amount copied off the contract is exactly the shape the old code had, and it
looked correct while settling nothing.

Settlement is derived, never stored, so the reversal tests are the load-bearing
ones: cancel the payment and the operational status must follow the ledger with no
reversal code involved.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.logistay.api import contract_billing
from apex.tests import factories
from apex.tests.factories import service_item

test_ignore = ["Company", "Supplier", "Currency", "Cost Center", "Project", "Item"]


class _PaymentCase(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.company = factories.make_company("Test AFMCO").name
        cls.supplier = factories.make_supplier("QA Telecom Operator")
        cls.other_supplier = factories.make_supplier("QA Other Operator")
        cls.item = service_item("QA Telecom Service")
        cls.cost_center = frappe.db.get_value("Company", cls.company, "cost_center")
        cash = frappe.db.get_value(
            "Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
        )
        if cash:
            frappe.db.set_value("Company", cls.company, "default_cash_account", cash)

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.db.savepoint("telecom_payment_test")

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback(save_point="telecom_payment_test")

    # Fixtures

    def contract(self, company=None, supplier=None, submit=True):
        doc = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "naming_series": "TEL-CTR-.YYYY.-.#####",
                "company": company or self.company,
                "supplier": supplier or self.supplier,
                "contract_start_date": "2026-01-01",
                "contract_end_date": "2026-12-31",
                "billing_frequency": "Monthly",
                "recurring_amount": 250,
                "currency": "SAR",
                "service_item": self.item,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        if submit:
            doc.submit()
        return doc

    def invoice(self, company=None, supplier=None, rate=250, submit=True):
        """A Purchase Invoice for the telecom service. Accounts are left to
        ERPNext's own set_missing_values so the fixture never diverges from how a
        real invoice is built on this site."""
        company = company or self.company
        doc = frappe.get_doc(
            {
                "doctype": "Purchase Invoice",
                "company": company,
                "supplier": supplier or self.supplier,
                "posting_date": today(),
                "due_date": today(),
                "currency": "SAR",
                "items": [
                    {
                        "item_code": self.item,
                        "qty": 1,
                        "rate": rate,
                        # The cost center must belong to the INVOICE's company: the
                        # cross-company test would otherwise fail inside ERPNext's own
                        # validation instead of at the guard it is aimed at.
                        "cost_center": frappe.db.get_value("Company", company, "cost_center"),
                    }
                ],
            }
        )
        doc.set_missing_values()
        doc.insert(ignore_permissions=True)
        if submit:
            doc.submit()
        return doc

    @staticmethod
    def payment_count(supplier):
        """Payment Entries for a supplier, COUNTED. 'A payment exists' is equally
        true after a double post, so every refusal test counts instead of looking."""
        return frappe.db.count("Payment Entry", {"party_type": "Supplier", "party": supplier})


class TestAPaymentIsAllocatedToItsInvoice(_PaymentCase):
    def test_the_payment_carries_one_allocated_reference_to_the_invoice(self):
        contract = self.contract()
        invoice = self.invoice()
        result = contract_billing.create_payment_entry(contract.name, "2026-07", invoice.name)

        payment = frappe.get_doc("Payment Entry", result["document_name"])
        self.assertEqual(payment.docstatus, 0, "Apex must never submit the payment itself")
        self.assertEqual(payment.payment_type, "Pay")
        self.assertEqual(payment.party, self.supplier)
        # The whole point: exactly one reference, pointing at the invoice, allocated.
        self.assertEqual(len(payment.references), 1)
        reference = payment.references[0]
        self.assertEqual(reference.reference_doctype, "Purchase Invoice")
        self.assertEqual(reference.reference_name, invoice.name)
        self.assertGreater(reference.allocated_amount, 0)
        self.assertEqual(reference.allocated_amount, invoice.outstanding_amount)

    def test_the_result_names_the_doctype_it_actually_created(self):
        """The old action was labelled 'Payment Order' while creating a Payment
        Entry — and ERPNext has a SEPARATE Payment Order DocType, so the label named
        a different document than the one on screen."""
        contract = self.contract()
        invoice = self.invoice()
        result = contract_billing.create_payment_entry(contract.name, "2026-07", invoice.name)
        self.assertEqual(result["document_type"], "Payment Entry")
        self.assertTrue(frappe.db.exists("Payment Entry", result["document_name"]))

    def test_the_recorded_amount_is_the_allocation_not_the_contract_rate(self):
        """A contract charging 250 against an invoice for 400 must record what was
        actually allocated. The old code copied recurring_amount and allocated
        nothing, so the log agreed with the contract and not with the ledger."""
        contract = self.contract()
        invoice = self.invoice(rate=400)
        contract_billing.create_payment_entry(contract.name, "2026-07", invoice.name)

        contract.reload()
        row = next(r for r in contract.billing_documents if r.document_type == "Payment Entry")
        self.assertEqual(row.amount, invoice.outstanding_amount)
        self.assertNotEqual(row.amount, contract.recurring_amount)

    def test_a_second_call_for_the_period_returns_the_same_draft(self):
        contract = self.contract()
        invoice = self.invoice()
        first = contract_billing.create_payment_entry(contract.name, "2026-07", invoice.name)
        before = self.payment_count(self.supplier)
        again = contract_billing.create_payment_entry(contract.name, "2026-07", invoice.name)

        self.assertTrue(again["existing"])
        self.assertEqual(again["document_name"], first["document_name"])
        # Idempotent means NO second document, not merely the same name returned.
        self.assertEqual(self.payment_count(self.supplier), before)


class TestAPaymentWithoutAPayableIsRefused(_PaymentCase):
    def _refuse(self, contract, invoice_name, expected_fragment):
        before = self.payment_count(self.supplier)
        with self.assertRaises(frappe.ValidationError) as caught:
            contract_billing.create_payment_entry(contract.name, "2026-07", invoice_name)
        # Assert the MESSAGE: a link check raises the same ValidationError class and
        # would satisfy a bare assertRaises while proving nothing about the guard.
        self.assertIn(expected_fragment, str(caught.exception))
        self.assertEqual(self.payment_count(self.supplier), before)
        contract.reload()
        self.assertFalse(
            [r for r in contract.billing_documents if r.document_type == "Payment Entry"],
            "a refused payment must leave no billing log row behind",
        )

    def test_no_invoice_at_all_is_refused(self):
        self._refuse(self.contract(), None, "Purchase Invoice")

    def test_an_empty_invoice_name_is_refused(self):
        self._refuse(self.contract(), "", "Purchase Invoice")

    def test_a_draft_invoice_cannot_be_paid(self):
        contract = self.contract()
        draft = self.invoice(submit=False)
        self._refuse(contract, draft.name, "not submitted")

    def test_another_supplier_s_invoice_cannot_be_paid(self):
        contract = self.contract()
        foreign = self.invoice(supplier=self.other_supplier)
        self._refuse(contract, foreign.name, "billed by")

    def test_an_already_settled_invoice_cannot_be_paid_again(self):
        contract = self.contract()
        invoice = self.invoice()
        frappe.db.set_value("Purchase Invoice", invoice.name, "outstanding_amount", 0)
        self._refuse(contract, invoice.name, "already settled")

    def test_a_missing_invoice_is_refused(self):
        self._refuse(self.contract(), "PINV-DOES-NOT-EXIST", "does not exist")

    def test_another_company_s_invoice_cannot_be_paid(self):
        other_company = factories.make_company("Other AFMCO", abbr="OAFM").name
        contract = self.contract()
        foreign = self.invoice(company=other_company)
        before = self.payment_count(self.supplier)
        with self.assertRaises(frappe.ValidationError) as caught:
            contract_billing.create_payment_entry(contract.name, "2026-07", foreign.name)
        self.assertIn("company", str(caught.exception))
        self.assertEqual(self.payment_count(self.supplier), before)

    def test_a_draft_contract_raises_no_payment(self):
        contract = self.contract(submit=False)
        invoice = self.invoice()
        with self.assertRaises(frappe.ValidationError) as caught:
            contract_billing.create_payment_entry(contract.name, "2026-07", invoice.name)
        self.assertIn("submitted contract", str(caught.exception))


class TestTheActionFailsClosedWithNoPayable(_PaymentCase):
    def test_no_outstanding_invoice_means_an_empty_eligible_list(self):
        """The empty list is what hides the action in the form: with nothing to
        allocate against, the operator is told to raise the invoice instead of being
        handed a document that settles nothing."""
        contract = self.contract()
        self.assertEqual(contract_billing.list_payable_invoices(contract.name), [])

    def test_only_this_contract_s_own_supplier_appears(self):
        contract = self.contract()
        mine = self.invoice()
        self.invoice(supplier=self.other_supplier)
        names = [row["name"] for row in contract_billing.list_payable_invoices(contract.name)]
        self.assertEqual(names, [mine.name])

    def test_a_settled_invoice_drops_out_of_the_eligible_list(self):
        contract = self.contract()
        invoice = self.invoice()
        self.assertIn(
            invoice.name, [r["name"] for r in contract_billing.list_payable_invoices(contract.name)]
        )
        frappe.db.set_value("Purchase Invoice", invoice.name, "outstanding_amount", 0)
        self.assertEqual(contract_billing.list_payable_invoices(contract.name), [])


class TestSettlementFollowsTheLedger(_PaymentCase):
    """Settlement is DERIVED from the live Payment Entry. These prove the derivation
    both ways — it must not report settled before the ledger says so, and it must
    stop reporting settled the moment the ledger stops saying so."""

    def test_a_period_with_no_payment_is_not_raised(self):
        contract = self.contract()
        status = contract_billing.get_billing_status(contract.name, "2026-07")
        self.assertEqual(status["settlement"], contract_billing.NOT_RAISED)
        self.assertIsNone(status["payment_entry"])

    def test_a_draft_payment_is_awaiting_approval_not_settled(self):
        contract = self.contract()
        invoice = self.invoice()
        contract_billing.create_payment_entry(contract.name, "2026-07", invoice.name)
        status = contract_billing.get_billing_status(contract.name, "2026-07")
        self.assertEqual(status["settlement"], contract_billing.AWAITING_APPROVAL)

    def test_settled_only_after_the_payment_is_submitted(self):
        contract = self.contract()
        invoice = self.invoice()
        result = contract_billing.create_payment_entry(contract.name, "2026-07", invoice.name)

        payment = frappe.get_doc("Payment Entry", result["document_name"])
        payment.submit()

        status = contract_billing.get_billing_status(contract.name, "2026-07")
        self.assertEqual(status["settlement"], contract_billing.SETTLED)
        self.assertGreater(status["allocated_amount"], 0)
        # The ledger agrees: the invoice it settled is no longer outstanding.
        self.assertEqual(
            frappe.db.get_value("Purchase Invoice", invoice.name, "outstanding_amount"), 0
        )

    def test_cancelling_the_payment_reverses_the_settlement(self):
        """No reversal code exists, and that is the point: the status is read from
        the Payment Entry, so cancelling it in Accounts is the whole reversal."""
        contract = self.contract()
        invoice = self.invoice()
        result = contract_billing.create_payment_entry(contract.name, "2026-07", invoice.name)
        payment = frappe.get_doc("Payment Entry", result["document_name"])
        payment.submit()
        self.assertEqual(
            contract_billing.get_billing_status(contract.name, "2026-07")["settlement"],
            contract_billing.SETTLED,
        )

        payment.reload()
        payment.cancel()

        status = contract_billing.get_billing_status(contract.name, "2026-07")
        self.assertEqual(status["settlement"], contract_billing.REVERSED)
        # The invoice is outstanding again — operational status and ledger agree.
        self.assertGreater(
            frappe.db.get_value("Purchase Invoice", invoice.name, "outstanding_amount"), 0
        )

    def test_a_submitted_payment_with_no_allocation_is_never_called_settled(self):
        """The regression this card exists for. An on-account Payment Entry can be
        submitted perfectly happily; it just settles nothing. Reporting it as settled
        is the false claim, so the derivation must refuse it even at docstatus 1."""
        from erpnext.accounts.doctype.payment_entry.payment_entry import (
            get_default_bank_cash_account,
        )
        from erpnext.accounts.party import get_party_account

        contract = self.contract()
        paid_from = (
            get_default_bank_cash_account(self.company, "Cash")
            or get_default_bank_cash_account(self.company, "Bank")
        )["account"]
        on_account = frappe.new_doc("Payment Entry")
        on_account.payment_type = "Pay"
        on_account.company = self.company
        on_account.posting_date = today()
        on_account.party_type = "Supplier"
        on_account.party = self.supplier
        on_account.paid_from = paid_from
        on_account.paid_to = get_party_account("Supplier", self.supplier, self.company)
        on_account.paid_amount = 250
        on_account.received_amount = 250
        on_account.cost_center = self.cost_center
        on_account.setup_party_account_field()
        on_account.set_missing_values()
        on_account.insert(ignore_permissions=True)
        on_account.submit()
        self.assertEqual(len(on_account.references), 0, "fixture must be genuinely unallocated")

        contract.append(
            "billing_documents",
            {
                "billing_period": "2026-07",
                "document_type": "Payment Entry",
                "document_name": on_account.name,
                "amount": 250,
                "currency": "SAR",
            },
        )
        contract.flags.ignore_validate_update_after_submit = True
        contract.save(ignore_permissions=True)

        status = contract_billing.get_billing_status(contract.name, "2026-07")
        self.assertNotEqual(status["settlement"], contract_billing.SETTLED)
        self.assertEqual(status["settlement"], contract_billing.AWAITING_APPROVAL)
        self.assertEqual(status["allocated_amount"], 0)


class TestTheLedgerOutranksTheBillingLog(_PaymentCase):
    """The billing row is HISTORY, not ownership. It must not veto Accounts
    cancelling the payment — and the exemption that allows that must stay narrow
    enough that the row can never end up pointing at a document that is gone.
    """

    def settled_payment(self):
        contract = self.contract()
        invoice = self.invoice()
        result = contract_billing.create_payment_entry(contract.name, "2026-07", invoice.name)
        payment = frappe.get_doc("Payment Entry", result["document_name"])
        payment.submit()
        return contract, payment

    def test_the_cancel_exemption_is_wired_to_payment_entry(self):
        """A correct handler nobody calls is not a fix. Naming the wiring here means
        an unwired hook fails as itself rather than as a puzzling LinkExistsError."""
        # get_doc_hooks is the exact lookup run_method uses (document.py:1367).
        handlers = frappe.get_doc_hooks().get("Payment Entry", {}).get("on_cancel", [])
        self.assertIn(
            "apex.logistay.api.contract_billing.allow_cancel_despite_billing_log", handlers
        )

    def test_the_billing_row_survives_the_cancellation_as_history(self):
        """Reversal is DERIVED, so the row is never cleared: erasing it would erase
        the audit trail of which payment was raised and later reversed."""
        contract, payment = self.settled_payment()
        payment.reload()
        payment.cancel()

        contract.reload()
        row = next(r for r in contract.billing_documents if r.document_type == "Payment Entry")
        self.assertEqual(row.document_name, payment.name)

    def test_a_cancelled_payment_the_contract_still_cites_cannot_be_deleted(self):
        """The load-bearing guard on the exemption's SCOPE. Frappe reads
        ignore_linked_doctypes only when cancelling, so deletion stays blocked and the
        billing row cannot be orphaned. Widening the exemption to deletes reds here.
        """
        contract, payment = self.settled_payment()
        payment.reload()
        payment.cancel()

        with self.assertRaises(frappe.LinkExistsError):
            frappe.delete_doc("Payment Entry", payment.name)
        self.assertTrue(frappe.db.exists("Payment Entry", payment.name))

    def test_the_exemption_keeps_erpnext_s_own_ledger_entries(self):
        """Assigning instead of appending would drop GL Entry and Payment Ledger Entry
        from the list ERPNext builds in its own on_cancel, breaking EVERY Payment Entry
        cancellation on the site — telecom or not."""
        payment = frappe.new_doc("Payment Entry")
        payment.ignore_linked_doctypes = ("GL Entry", "Payment Ledger Entry")

        contract_billing.allow_cancel_despite_billing_log(payment)

        self.assertIn("Telecom Contract", payment.ignore_linked_doctypes)
        self.assertIn("GL Entry", payment.ignore_linked_doctypes)
        self.assertIn("Payment Ledger Entry", payment.ignore_linked_doctypes)

    def test_the_exemption_is_added_once_however_often_it_runs(self):
        payment = frappe.new_doc("Payment Entry")
        contract_billing.allow_cancel_despite_billing_log(payment)
        contract_billing.allow_cancel_despite_billing_log(payment)
        self.assertEqual(list(payment.ignore_linked_doctypes).count("Telecom Contract"), 1)
