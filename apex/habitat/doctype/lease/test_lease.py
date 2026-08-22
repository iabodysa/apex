# Copyright (c) 2026, AFMCO and contributors
"""Lease core lifecycle: creation/validation, the payment-schedule generator, what a
refused schedule regeneration must not cost the rest of the request, and that every
status the Workflow can be driven into (including the scheduler's own Expired write)
is one the Workflow itself knows about."""
from __future__ import annotations
import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today
from unittest import TestCase
from unittest.mock import MagicMock, patch
from apex.apex_core.utils import payable_allocation
from apex.habitat.doctype.lease import lease_payment
from apex.tests import factories
from apex.tests.factories import service_item

class TestAccommodationLease(FrappeTestCase):

    def test_create_valid_lease(self):
        doc = frappe.get_doc({
            "doctype": "Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": "QA-BLDG",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-12-31",
            "rent_amount": 8000,
            "first_payment_date": "2026-01-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.rent_amount, 8000)
        frappe.delete_doc("Lease", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_raises(self):
        doc = frappe.get_doc({
            "doctype": "Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-12-31",
            "rent_amount": 5000,
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_end_date_before_start_date_raises(self):
        from apex.habitat.doctype.lease.lease import validate

        doc = frappe.get_doc({
            "doctype": "Lease",
            "building": "QA-BLDG",
            "lease_start_date": "2026-06-01",
            "lease_end_date": "2026-05-01",
            "rent_amount": 5000,
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_schedule_rows_default_unpaid(self):
        """Generated schedule rows are stamped 'Unpaid', never 'Paid'. The
        'Generate Payment' button selects the next non-Paid row, so a fresh row
        must read Unpaid for that selection to land on it (guards the row-pick
        contract the form button depends on)."""
        from apex.habitat.doctype.lease.lease import _build_schedule

        doc = frappe.get_doc({
            "doctype": "Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": "QA-BLDG",
            "lease_start_date": "2026-01-01",
            "lease_end_date": "2026-06-30",
            "rent_amount": 4000,
            "first_payment_date": "2026-01-01",
            "billing_cycle": "Monthly",
        })
        _build_schedule(doc)
        self.assertTrue(doc.payment_schedule)
        self.assertTrue(all(r.status == "Unpaid" for r in doc.payment_schedule))

class TestRegenerateScheduleFailure(FrappeTestCase):
    """What a REFUSED ``regenerate_schedule`` costs the rest of the request.

    The endpoint must not wrap its ``doc.save()`` in ``except Exception:
    frappe.db.rollback(); frappe.throw(generic)``: ``frappe.db.rollback()`` takes no
    savepoint, so it would discard the WHOLE request transaction — every row written
    before this endpoint was reached, not just the lease — and report "Could not
    save changes" in place of the validation error that actually refused the save.

    The refusal below is real, not injected: an existing lease is widened into an
    overlap with ``frappe.db.set_value`` (which skips validate), which is how live
    data drifts underneath a draft somebody left open.
    """

    def _hash(self):
        return frappe.generate_hash(length=12).upper()

    def _witness_row(self):
        """A Site row: one mandatory Data field, no links, untouched by anything else
        here, so its survival isolates the transaction behaviour."""
        return frappe.get_doc({
            "doctype": "Site", "site_name": "A333-LEASE-" + self._hash(),
        }).insert(ignore_permissions=True).name

    def _building(self):
        return frappe.get_doc({
            "doctype": "Building", "building_name": "B " + self._hash(), "total_capacity": 4,
        }).insert(ignore_permissions=True).name

    def _draft_lease(self, building, start, end):
        return frappe.get_doc({
            "doctype": "Lease",
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": building,
            "lease_start_date": start,
            "lease_end_date": end,
            "rent_amount": 6000,
            "billing_cycle": "Monthly",
            "first_payment_date": start,
        }).insert(ignore_permissions=True)

    def test_a_refused_regeneration_keeps_rows_written_earlier_in_the_same_request(self):
        from apex.habitat.doctype.lease.lease import regenerate_schedule

        witness = self._witness_row()
        building = self._building()
        lease = self._draft_lease(building, "2026-01-01", "2026-12-31")
        rival = self._draft_lease(building, "2027-01-01", "2027-12-31")
        frappe.db.set_value("Lease", rival.name, "lease_start_date", "2026-06-01")

        with self.assertRaises(frappe.ValidationError) as caught:
            regenerate_schedule(lease.name)

        self.assertIn(
            rival.name, str(caught.exception),
            "the caller must be told WHICH lease overlaps, not a generic 'could not "
            "save changes' standing in for it",
        )
        self.assertTrue(
            frappe.db.exists("Site", witness),
            "a refused regeneration must not discard rows this request wrote before it",
        )
        self.assertTrue(
            frappe.db.exists("Lease", rival.name),
            "the overlapping lease that caused the refusal must survive it",
        )

WORKFLOW = "Lease Workflow"

def _h(n=12):
    return frappe.generate_hash(length=n).upper()

class TestTheWorkflowOwnsEveryStatusItIsGiven(FrappeTestCase):
    """the scheduler must not write a status the Workflow cannot validate.

    `status` on Lease is the Workflow's state field, and the Lease Workflow knows four
    states: Draft, Pending Approval, Approved, Rejected. The Select allows three more —
    Active, Expired, Terminated — and `lease_expiry_watchlist` writes Expired straight to
    the database. The document then sits in a value its own state machine does not contain.

    The failing sequence the card names is the first test here: approve a lease, backdate
    its end date, run the job, then open and save it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.site = frappe.get_doc(
            {"doctype": "Site", "site_name": "LS " + _h()}
        ).insert(ignore_permissions=True).name

    def _building(self):
        doc = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "LS " + _h(),
                "site": self.site,
                "status": "Active",
                "total_capacity": 2,
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    def _drop_lease(self, name):
        """A submitted record refuses deletion, so the fixture cancels first. `db_set`
        clears the docstatus without asking the Workflow for a cancel transition it has
        no action for."""
        frappe.db.set_value("Lease", name, "docstatus", 0, update_modified=False)
        frappe.delete_doc("Lease", name, force=True, ignore_permissions=True)

    def _expired_lease(self):
        doc = frappe.get_doc(
            {
                "doctype": "Lease",
                "building": self._building(),
                "lease_start_date": add_days(today(), -60),
                "lease_end_date": add_days(today(), -1),
                "rent_amount": 100,
                "billing_cycle": "Monthly",
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(self._drop_lease, doc.name)
        apply_workflow(doc, "Submit for Approval")
        apply_workflow(doc, "Approve")
        self.assertEqual(doc.docstatus, 1, "the fixture must be a submitted lease")
        self.assertEqual(doc.status, "Approved")
        return doc

    def test_every_status_the_select_allows_is_a_workflow_state(self):
        """The root of it. A value the Select permits but the Workflow does not know is
        a value the document can hold and the state machine cannot reason about."""
        allowed = {
            o.strip()
            for o in (frappe.get_meta("Lease").get_field("status").options or "").split("\n")
            if o.strip()
        }
        states = set(
            frappe.get_all(
                "Workflow Document State",
                filters={"parent": WORKFLOW},
                pluck="state",
            )
        )
        self.assertEqual(
            sorted(allowed - states),
            [],
            "the Select allows statuses the Lease Workflow has no state for",
        )

    def test_the_workflow_state_field_really_is_status(self):
        """If this ever changes, the test above is measuring the wrong field."""
        self.assertEqual(
            frappe.db.get_value("Workflow", WORKFLOW, "workflow_state_field"), "status"
        )

    def test_the_scheduler_leaves_the_lease_saveable(self):
        """The failing sequence from the card, end to end."""
        from apex.habitat.tasks.residency import lease_expiry_watchlist

        lease = self._expired_lease()
        lease_expiry_watchlist()
        lease.reload()
        self.assertEqual(lease.status, "Expired", "the job did not run on this fixture")
        lease.save(ignore_permissions=True)
        lease.reload()
        self.assertEqual(
            lease.status,
            "Expired",
            "saving the lease moved it off the status the scheduler set",
        )

test_ignore = ['Additional Salary', 'Asset', 'Asset Movement', 'Company', 'Cost Center', 'Currency', 'Employee', 'Item', 'Payment Entry', 'Project', 'Purchase Invoice', 'Role', 'Salary Component', 'Supplier', 'User']

FIRST_DUE = "2026-01-01"
SECOND_DUE = "2026-02-01"
RENT = 8000
INVOICE_TOTAL = 5500
ROUTING_SETTINGS = "Payment Routing Settings"
TARGET_FIELD = "target_payment_doctype"
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
        self.route_payments_to(payable_allocation.PAYMENT_ENTRY_DOCTYPE)

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback(save_point="lease_payment_test")

    def route_payments_to(self, target_doctype):
        """Point Payment Routing Settings at ``target_doctype`` for one test.

        The restore is registered BEFORE the write and goes back through the same
        setter, because a Single is not a row this suite's savepoint can undo on its
        own: ``set_single_value`` clears the document cache as it writes, so a rolled
        back ``tabSingles`` would still be read back through whatever the last writer
        cached. Blank is passed as "" rather than None — it is what an unconfigured
        router actually holds, and the router reads it as the Payment Request default.
        """
        original = frappe.db.get_single_value(ROUTING_SETTINGS, TARGET_FIELD) or ""
        self.addCleanup(frappe.db.set_single_value, ROUTING_SETTINGS, TARGET_FIELD, original)
        frappe.db.set_single_value(ROUTING_SETTINGS, TARGET_FIELD, target_doctype)

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
    def _refuse(self, lease, invoice_name, expected_fragment, due_date=FIRST_DUE, facet=None):
        before = self.payment_count(self.landlord)
        with self.assertRaises(frappe.ValidationError) as caught:
            lease_payment.create_rent_payment(lease.name, due_date, invoice_name)
        if facet:
            self.assertIn(expected_fragment, str(caught.exception), facet)
            self.assertEqual(self.payment_count(self.landlord), before, facet)
        else:
            self.assertIn(expected_fragment, str(caught.exception))
            self.assertEqual(self.payment_count(self.landlord), before)

    def test_a_missing_invoice_reference_is_refused_whether_null_or_empty(self):
        """``load_eligible_payable`` guards with ``if not purchase_invoice`` — one
        falsy check, not an ``is None`` check — so both shapes a caller can send for
        "nothing selected" must hit the SAME line (payable_allocation.py:87-94)."""
        self._refuse(self.lease(), None, "Purchase Invoice",
                     facet="a None invoice_name is refused")
        self._refuse(self.lease(), "", "Purchase Invoice",
                     facet="an empty-string invoice_name is refused")

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
class TestTheRentSurfaceObeysTheConfiguredPaymentTarget(_RentPaymentCase):
    """A deployment configures one payment target; this screen must not raise another.

    The exposure was bounded — the old branches opened UNSAVED drafts, so nothing was
    written behind the operator's back. What diverged was the document TYPE: the
    configuration said one thing and this one surface did another.
    """

    def _refuse(self, callable_, *args):
        """Run a rent action that must be refused, and prove no payment came of it."""
        before = self.payment_count(self.landlord)
        with self.assertRaises(frappe.ValidationError) as caught:
            callable_(*args)
        self.assertEqual(self.payment_count(self.landlord), before)
        return str(caught.exception)

    def test_changing_the_configured_target_changes_what_this_surface_opens(self):
        """The pair the card turns on. Same lease, same invoice, two configurations —
        so the outcome can only be attributed to the configuration."""
        lease = self.lease()
        invoice = self.invoice()

        self.route_payments_to("Payment Request")
        self._refuse(lease_payment.create_rent_payment, lease.name, FIRST_DUE, invoice.name)

        self.route_payments_to(payable_allocation.PAYMENT_ENTRY_DOCTYPE)
        result = lease_payment.create_rent_payment(lease.name, FIRST_DUE, invoice.name)
        self.assertEqual(result["document_type"], payable_allocation.PAYMENT_ENTRY_DOCTYPE)
        self.assertFalse(result["existing"])

    def test_the_unconfigured_router_default_is_refused_not_quietly_paid(self):
        """The first case the card names. An unconfigured router answers Payment
        Request; the old button had no branch for that answer, so it fell through to
        the else branch and opened a Payment Entry — the configured default ignored on
        the one screen that read it."""
        self.route_payments_to("")
        message = self._refuse(
            lease_payment.create_rent_payment, self.lease().name, FIRST_DUE, self.invoice().name
        )
        self.assertIn("Payment Request", message)

    def test_a_client_custom_target_is_refused_by_name(self):
        """The router supports any client payment DocType, so the refusal cannot be a
        whitelist of the two the old branches knew. It names whatever is configured."""
        self.route_payments_to("Payment Order")
        message = self._refuse(
            lease_payment.create_rent_payment, self.lease().name, FIRST_DUE, self.invoice().name
        )
        self.assertIn("Payment Order", message)
        self.assertIn(ROUTING_SETTINGS, message)

    def test_a_mismatched_target_stops_the_action_before_the_dialog_opens(self):
        """The refusal has to reach the button, not just the writer. The eligible-payable
        listing is the first call the button makes, so gating there is what stops an
        operator filling in a dialog whose submit could only fail."""
        lease = self.lease()
        self.invoice()
        self.route_payments_to("Payment Order")
        self.assertIn("Payment Order", self._refuse(lease_payment.list_rent_payables, lease.name))

    def test_the_status_read_is_refused_too(self):
        """One gate on the path all three endpoints share, so no endpoint can be added
        later that reads or writes rent payments without passing it."""
        lease = self.lease()
        self.route_payments_to("Payment Order")
        self._refuse(lease_payment.get_rent_payment_status, lease.name, FIRST_DUE)
class TestRentPaymentDuplicateProbeLocks(TestCase):
    def _probe_kwargs(self, endpoint, *args):
        fake = MagicMock()
        fake.db.get_value.return_value = "PE-1"
        lease_doc = MagicMock(company="C", landlord="L")
        lease_doc.name = "LEASE-1"
        row = frappe._dict(due_date="2026-09-01", amount=1000)

        with (
            patch.object(lease_payment, "frappe", fake),
            patch.object(lease_payment, "_load_eligible_lease", return_value=lease_doc),
            patch.object(lease_payment, "_instalment", return_value=row),
            patch.object(lease_payment, "payable_allocation") as allocation,
        ):
            allocation.PAYMENT_ENTRY_DOCTYPE = "Payment Entry"
            allocation.settlement_of.return_value = {}
            allocation.payable_count.return_value = 0
            getattr(endpoint, "__wrapped__", endpoint)(*args)

        probes = [
            call
            for call in fake.db.get_value.call_args_list
            if call.args and call.args[0] == "Payment Entry"
        ]
        self.assertEqual(len(probes), 1, "the instalment is probed exactly once")
        return probes[0]

    def test_the_create_path_probes_payment_entry_under_a_lock(self):
        probe = self._probe_kwargs(
            lease_payment.create_rent_payment, "LEASE-1", "2026-09-01"
        )
        self.assertTrue(
            probe.kwargs.get("for_update"),
            "an unlocked probe reads a snapshot older than the Lease lock it sits behind",
        )

    def test_the_status_path_takes_no_lock(self):
        probe = self._probe_kwargs(
            lease_payment.get_rent_payment_status, "LEASE-1", "2026-09-01"
        )
        self.assertFalse(
            probe.kwargs.get("for_update"),
            "a read-only status endpoint must not lock rows it never writes",
        )
