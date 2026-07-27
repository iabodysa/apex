# Copyright (c) 2026, AFMCO and contributors
"""A rent payment must settle a real landlord payable, not sit on account.

The Generate Payment button used to build the Payment Entry in the browser with
``paid_amount = selected.amount || rent_amount``. That document had no ``references``
row, so it was an ON-ACCOUNT payment: it closed no invoice, moved no
``outstanding_amount``, and reconciled nothing — while carrying exactly the rent figure
the operator expected to see, which is why nobody re-read it.

So these cases check the ALLOCATION, never the amount. The load-bearing one is
``test_the_allocation_is_the_invoice_not_the_rent_schedule``: it deliberately gives the
lease and the invoice DIFFERENT figures, because a fixture where they agree passes for
the old code too.

The reversal cases are the other half. Settlement is derived from the live Payment
Entry, so cancelling it in Accounts must reverse the lease's view with no reversal code
running — and, unlike the Telecom Contract, no cancel exemption either: the lease stores
no link to the payment, so nothing on it can veto the cancellation.

Every submitted lease here is approved through ``apply_workflow``. Lease is governed by
the Accommodation Lease Workflow, so a bare ``doc.submit()`` is refused by
``apex_core.utils.workflow_guard`` — and reaching docstatus 1 any other way would build
a fixture in a state no approver can actually produce.
"""

from __future__ import annotations

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.apex_core.utils import payable_allocation
from apex.habitat.doctype.lease import lease_payment
from apex.tests import factories
from apex.tests.factories import service_item

test_ignore = [
    "Company",
    "Supplier",
    "Currency",
    "Cost Center",
    "Project",
    "Item",
    "Payment Entry",
    "Purchase Invoice",
]

FIRST_DUE = "2026-01-01"
SECOND_DUE = "2026-02-01"
# The rent and the invoice deliberately DISAGREE: a fixture where they match cannot
# tell an allocated payment apart from an amount copied off the schedule.
RENT = 8000
INVOICE_TOTAL = 5500
# Distinguishes "the caller did not choose a landlord" from "the caller chose none",
# which is a real lease state: the field is not mandatory.
_UNSET = object()


class _RentPaymentCase(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.company = factories.make_company("Test AFMCO").name
        cls.landlord = factories.make_supplier("QA Building Landlord")
        cls.other_landlord = factories.make_supplier("QA Other Landlord")
        cls.item = service_item("QA Building Rent")
        cash = frappe.db.get_value(
            "Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
        )
        if cash:
            frappe.db.set_value("Company", cls.company, "default_cash_account", cash)

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.db.savepoint("lease_payment_test")

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback(save_point="lease_payment_test")

    # Fixtures

    def building(self):
        suffix = frappe.generate_hash(length=12).upper()
        return frappe.get_doc(
            {"doctype": "Building", "building_name": "RENT " + suffix, "total_capacity": 4}
        ).insert(ignore_permissions=True).name

    def lease(self, landlord=_UNSET, company=None, submit=True):
        """A lease with a monthly schedule starting at FIRST_DUE.

        Approved through the workflow, never bare-submitted: Draft -> Submit for
        Approval -> Approve is the only route to docstatus 1 the product offers, and the
        Approved state is what ``_load_eligible_lease`` demands.
        """
        doc = frappe.get_doc(
            {
                "doctype": "Lease",
                "naming_series": "ACC-LEASE-.YYYY.-.####",
                "company": company or self.company,
                "building": self.building(),
                "landlord": self.landlord if landlord is _UNSET else landlord,
                "status": "Draft",
                "lease_start_date": FIRST_DUE,
                "lease_end_date": "2026-06-30",
                "rent_amount": RENT,
                "billing_cycle": "Monthly",
                "first_payment_date": FIRST_DUE,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        if submit:
            apply_workflow(doc, "Submit for Approval")
            apply_workflow(doc, "Approve")
            doc.reload()
        return doc

    def invoice(self, company=None, landlord=None, total=INVOICE_TOTAL, submit=True):
        """A landlord Purchase Invoice, built through ERPNext's own set_missing_values
        so the fixture never diverges from how a real invoice is raised on this site."""
        company = company or self.company
        doc = frappe.new_doc("Purchase Invoice")
        doc.company = company
        doc.supplier = landlord or self.landlord
        doc.posting_date = today()
        doc.due_date = today()
        doc.currency = "SAR"
        doc.append(
            "items",
            {
                "item_code": self.item,
                "qty": 1,
                "rate": total,
                # The cost center must belong to the INVOICE's company, or the
                # cross-company case fails inside ERPNext instead of at the guard.
                "cost_center": frappe.db.get_value("Company", company, "cost_center"),
            },
        )
        doc.set_missing_values()
        doc.insert(ignore_permissions=True)
        if submit:
            doc.submit()
        return doc

    @staticmethod
    def payment_count(landlord):
        """Payment Entries for a landlord, COUNTED. 'A payment exists' is equally true
        after a double post, so every refusal case counts rather than looks."""
        return frappe.db.count("Payment Entry", {"party_type": "Supplier", "party": landlord})


class TestARentPaymentIsAllocatedToItsInvoice(_RentPaymentCase):
    def test_the_payment_carries_one_allocated_reference_to_the_invoice(self):
        lease = self.lease()
        invoice = self.invoice()
        result = lease_payment.create_rent_payment(lease.name, FIRST_DUE, invoice.name)

        payment = frappe.get_doc("Payment Entry", result["document_name"])
        self.assertEqual(payment.docstatus, 0, "Apex must never submit the payment itself")
        self.assertEqual(payment.payment_type, "Pay")
        self.assertEqual(payment.party, self.landlord)
        self.assertEqual(len(payment.references), 1)
        reference = payment.references[0]
        self.assertEqual(reference.reference_doctype, "Purchase Invoice")
        self.assertEqual(reference.reference_name, invoice.name)
        self.assertEqual(reference.allocated_amount, invoice.outstanding_amount)

    def test_the_allocation_is_the_invoice_not_the_rent_schedule(self):
        """The regression this card exists for. The old button wrote the scheduled rent
        onto paid_amount and allocated nothing, so the payment agreed with the lease and
        not with the ledger."""
        lease = self.lease()
        invoice = self.invoice()
        result = lease_payment.create_rent_payment(lease.name, FIRST_DUE, invoice.name)

        payment = frappe.get_doc("Payment Entry", result["document_name"])
        allocated = payable_allocation.allocated_total(payment)
        self.assertEqual(allocated, invoice.outstanding_amount)
        self.assertNotEqual(allocated, lease.rent_amount)
        self.assertNotEqual(payment.paid_amount, lease.rent_amount)

    def test_the_payment_is_stamped_with_the_lease_and_the_instalment(self):
        """No field on the Lease holds the link, so these two ARE the link: without
        them the instalment could never be recognised as already raised."""
        lease = self.lease()
        result = lease_payment.create_rent_payment(lease.name, FIRST_DUE, self.invoice().name)

        payment = frappe.get_doc("Payment Entry", result["document_name"])
        self.assertEqual(payment.reference_no, lease.name)
        self.assertEqual(str(payment.reference_date), FIRST_DUE)

    def test_a_second_call_for_the_instalment_returns_the_same_draft(self):
        lease = self.lease()
        invoice = self.invoice()
        first = lease_payment.create_rent_payment(lease.name, FIRST_DUE, invoice.name)
        before = self.payment_count(self.landlord)
        again = lease_payment.create_rent_payment(lease.name, FIRST_DUE, invoice.name)

        self.assertTrue(again["existing"])
        self.assertEqual(again["document_name"], first["document_name"])
        # Idempotent means NO second document, not merely the same name returned.
        self.assertEqual(self.payment_count(self.landlord), before)

    def test_a_different_instalment_is_a_different_payment(self):
        """Idempotency must be per instalment, not per lease — otherwise month two can
        never be paid at all."""
        lease = self.lease()
        first = lease_payment.create_rent_payment(lease.name, FIRST_DUE, self.invoice().name)
        second = lease_payment.create_rent_payment(lease.name, SECOND_DUE, self.invoice().name)
        self.assertNotEqual(second["document_name"], first["document_name"])
        self.assertFalse(second["existing"])


class TestARentPaymentWithoutAPayableIsRefused(_RentPaymentCase):
    def _refuse(self, lease, invoice_name, expected_fragment, due_date=FIRST_DUE):
        before = self.payment_count(self.landlord)
        with self.assertRaises(frappe.ValidationError) as caught:
            lease_payment.create_rent_payment(lease.name, due_date, invoice_name)
        # Assert the MESSAGE: a link check raises the same ValidationError class and
        # would satisfy a bare assertRaises while proving nothing about the guard.
        self.assertIn(expected_fragment, str(caught.exception))
        self.assertEqual(self.payment_count(self.landlord), before)

    def test_no_invoice_at_all_is_refused(self):
        self._refuse(self.lease(), None, "Purchase Invoice")

    def test_an_empty_invoice_name_is_refused(self):
        self._refuse(self.lease(), "", "Purchase Invoice")

    def test_a_draft_invoice_cannot_be_paid(self):
        self._refuse(self.lease(), self.invoice(submit=False).name, "not submitted")

    def test_another_landlord_s_invoice_cannot_be_paid(self):
        self._refuse(self.lease(), self.invoice(landlord=self.other_landlord).name, "billed by")

    def test_an_already_settled_invoice_cannot_be_paid_again(self):
        invoice = self.invoice()
        frappe.db.set_value("Purchase Invoice", invoice.name, "outstanding_amount", 0)
        self._refuse(self.lease(), invoice.name, "already settled")

    def test_a_missing_invoice_is_refused(self):
        self._refuse(self.lease(), "PINV-DOES-NOT-EXIST", "does not exist")

    def test_another_company_s_invoice_cannot_be_paid(self):
        other = factories.make_company("Other AFMCO", abbr="OAFM").name
        self._refuse(self.lease(), self.invoice(company=other).name, "company")

    def test_an_instalment_the_lease_does_not_have_is_refused(self):
        """The due date is the period key. Accepting one the schedule never held would
        make the payment idempotent against nothing."""
        self._refuse(self.lease(), self.invoice().name, "no rent instalment", due_date="2027-09-01")

    def test_a_draft_lease_raises_no_payment(self):
        self._refuse(self.lease(submit=False), self.invoice().name, "submitted lease")

    def test_a_lease_with_no_landlord_raises_no_payment(self):
        """Without a party there is nobody to settle with, and the eligible-payable
        filter would otherwise match every unpaid invoice in the company."""
        self._refuse(self.lease(landlord=None), self.invoice().name, "Landlord")

    def test_a_lease_that_does_not_exist_is_refused(self):
        with self.assertRaises(frappe.ValidationError) as caught:
            lease_payment.list_rent_payables("ACC-LEASE-NOT-A-LEASE")
        self.assertIn("does not exist", str(caught.exception))


class TestTheRentActionFailsClosedWithNoPayable(_RentPaymentCase):
    """The empty list is what stops the dialog opening: with nothing to allocate
    against, the operator is told to raise the landlord invoice instead of being handed
    a document that settles nothing."""

    def test_no_outstanding_invoice_means_an_empty_eligible_list(self):
        self.assertEqual(lease_payment.list_rent_payables(self.lease().name), [])

    def test_only_this_lease_s_own_landlord_appears(self):
        lease = self.lease()
        mine = self.invoice()
        self.invoice(landlord=self.other_landlord)
        listed = [row["name"] for row in lease_payment.list_rent_payables(lease.name)]
        self.assertEqual(listed, [mine.name])

    def test_a_settled_invoice_drops_out_of_the_eligible_list(self):
        lease = self.lease()
        invoice = self.invoice()
        self.assertIn(invoice.name, [r["name"] for r in lease_payment.list_rent_payables(lease.name)])
        frappe.db.set_value("Purchase Invoice", invoice.name, "outstanding_amount", 0)
        self.assertEqual(lease_payment.list_rent_payables(lease.name), [])


class TestRentSettlementFollowsTheLedger(_RentPaymentCase):
    def test_an_instalment_with_no_payment_is_not_raised(self):
        status = lease_payment.get_rent_payment_status(self.lease().name, FIRST_DUE)
        self.assertEqual(status["settlement"], payable_allocation.NOT_RAISED)
        self.assertIsNone(status["payment_entry"])
        self.assertEqual(status["scheduled_amount"], RENT)

    def test_a_draft_payment_is_awaiting_approval_not_settled(self):
        lease = self.lease()
        lease_payment.create_rent_payment(lease.name, FIRST_DUE, self.invoice().name)
        status = lease_payment.get_rent_payment_status(lease.name, FIRST_DUE)
        self.assertEqual(status["settlement"], payable_allocation.AWAITING_APPROVAL)

    def test_settled_only_after_the_payment_is_submitted(self):
        lease = self.lease()
        invoice = self.invoice()
        result = lease_payment.create_rent_payment(lease.name, FIRST_DUE, invoice.name)
        frappe.get_doc("Payment Entry", result["document_name"]).submit()

        status = lease_payment.get_rent_payment_status(lease.name, FIRST_DUE)
        self.assertEqual(status["settlement"], payable_allocation.SETTLED)
        self.assertGreater(status["allocated_amount"], 0)
        # The ledger agrees: the invoice it settled is no longer outstanding.
        self.assertEqual(
            frappe.db.get_value("Purchase Invoice", invoice.name, "outstanding_amount"), 0
        )

    def test_cancelling_the_payment_reverses_the_settlement(self):
        """No reversal code exists, and that is the point: the status is read off the
        Payment Entry, so cancelling it in Accounts is the whole reversal.

        It also proves the lease never vetoes that cancellation. The Telecom Contract
        needed an ignore_linked_doctypes exemption because its billing log links to the
        payment; the lease stores no link, so there is nothing here to exempt.
        """
        lease = self.lease()
        invoice = self.invoice()
        result = lease_payment.create_rent_payment(lease.name, FIRST_DUE, invoice.name)
        payment = frappe.get_doc("Payment Entry", result["document_name"])
        payment.submit()

        payment.reload()
        payment.cancel()

        status = lease_payment.get_rent_payment_status(lease.name, FIRST_DUE)
        self.assertEqual(status["settlement"], payable_allocation.REVERSED)
        self.assertGreater(
            frappe.db.get_value("Purchase Invoice", invoice.name, "outstanding_amount"), 0
        )

    def test_a_cancelled_payment_still_holds_its_instalment(self):
        """The instalment is not silently freed for a second payment: the first one is
        cancelled in the ledger and the operator has to see that before re-raising."""
        lease = self.lease()
        result = lease_payment.create_rent_payment(lease.name, FIRST_DUE, self.invoice().name)
        payment = frappe.get_doc("Payment Entry", result["document_name"])
        payment.submit()
        payment.reload()
        payment.cancel()

        again = lease_payment.create_rent_payment(lease.name, FIRST_DUE, self.invoice().name)
        self.assertTrue(again["existing"])
        self.assertEqual(again["document_name"], result["document_name"])
