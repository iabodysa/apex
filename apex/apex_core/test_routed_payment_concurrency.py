# Copyright (c) 2026, AFMCO and contributors
"""Real two-connection concurrency test for routed-payment.

The ``test_routed_payment_serialization`` module asserts the duplicate-guard's
INVARIANT deterministically but, by its own docstring, does NOT reproduce a literal
DB row-lock race: a real ``SELECT ... FOR UPDATE`` block needs two live InnoDB
transactions, which threads sharing one test transaction cannot create. This file
closes that gap using the framework's two-connection harness
(``frappe.tests.utils.FrappeTestCase.primary_connection`` /
``secondary_connection`` -- the same mechanism ``frappe/tests/test_db.py::
TestConcurrency`` uses to test ``for_update`` contention).

The guarded section in ``apex_core.payment_router.route_payment``::

    frappe.db.get_value(SOURCE_DOCTYPE, payment_request, "name", for_update=True)
    source = frappe.get_doc(...)
    if source.linked_payment_entry:      # re-read-under-lock guard
        return source.linked_payment_entry
    ... create + (auto-)submit target ...
    source.db_set("linked_payment_entry", target.name)   # committed stamp

Two concurrent routes for one finance-approved request must not both build a
payment (a double-pay, and on the auto-submit path a double GL post). These tests
prove, against two real DB connections:

  * mutual exclusion -- while one transaction holds the source row lock, a second
    transaction's lock attempt is rejected (``QueryTimeoutError``); the two routes
    cannot run their critical sections at once; and
  * the merge outcome -- once the winner commits its ``linked_payment_entry``
    stamp, a second route in its own transaction re-reads it and returns the SAME
    payment, creating no second doc and no second ledger post.

A finance approval is modelled by stamping the immutable ``finance_approved_by``
the router gates on (the gate itself is proven in test_salis_payment_request_
workflow); fixtures key off ``self._testMethodName`` so parallel methods never
share a source row.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase, timeout

from apex.tests._helpers import submit_via_workflow

from apex.apex_core.payment_router import (
    LINK_DOCTYPE_FIELD,
    LINK_NAME_FIELD,
    SOURCE_DOCTYPE,
    route_payment,
)

SETTINGS = "Payment Routing Settings"
FIELD_MAP_CHILD = "Payment Routing Field Map"
STUB_DOCTYPE = "Test Routed Concurrency Stub"


def _make_stub_submittable_doctype():
    """Throwaway submittable target with a Currency + Data field. Idempotent."""
    if frappe.db.exists("DocType", STUB_DOCTYPE):
        return
    frappe.get_doc(
        {
            "doctype": "DocType",
            "name": STUB_DOCTYPE,
            "module": "Apex Core",
            "custom": 1,
            "is_submittable": 1,
            "autoname": "hash",
            "fields": [
                {"fieldname": "party", "fieldtype": "Data", "label": "Party"},
                {"fieldname": "paid_amount", "fieldtype": "Currency", "label": "Paid Amount"},
            ],
            "permissions": [
                {"role": "System Manager", "read": 1, "write": 1, "create": 1, "submit": 1}
            ],
        }
    ).insert(ignore_permissions=True)


class TestRoutedPaymentConcurrency(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        _make_stub_submittable_doctype()
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        # Reset the router as a PAIR before the stub goes: a target pointing at a
        # deleted DocType aborts every later save on _validate_links, and rows naming
        # stub fieldnames are then validated against the default Payment Request and
        # refused — both land on whichever module happens to run next.
        frappe.db.delete(FIELD_MAP_CHILD, {"parent": SETTINGS})
        frappe.db.set_single_value(SETTINGS, "target_payment_doctype", None)
        if frappe.db.exists("DocType", STUB_DOCTYPE):
            frappe.delete_doc("DocType", STUB_DOCTYPE, force=1, ignore_permissions=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
        s = frappe.get_single(SETTINGS)
        s.target_payment_doctype = STUB_DOCTYPE
        s.auto_submit_target = 1
        s.set(
            "field_map",
            [
                {"target_fieldname": "paid_amount", "source_fieldname": "amount"},
                {"target_fieldname": "party", "is_static": 1, "static_value": "AFMCO"},
            ],
        )
        s.save(ignore_permissions=True)
        apex = frappe.get_single("Apex Settings")
        apex.enable_gl_posting = 1
        apex.save(ignore_permissions=True)

    def _approved_request(self, **overrides):
        """A finance-STAMPED, submitted Salis Payment Request keyed to this test."""
        data = {
            "doctype": SOURCE_DOCTYPE,
            "expense_type": "Rental",
            "amount": 1000.00,
            "remarks": f"concurrency-{self._testMethodName}",
            "status": "Draft",
        }
        data.update(overrides)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True)
        # submit_via_workflow lands the sanctioned finance-approved submit state
        # (docstatus 1) past the workflow's finance-approval guard; stamp the approver
        # the router reads.
        submit_via_workflow(doc)
        doc.db_set("finance_approved_by", "Administrator", update_modified=False)
        doc.reload()
        return doc

    @timeout(15, "The router's source lock did not release / contend as expected")
    def test_concurrent_route_attempt_is_blocked_by_source_lock(self):
        """Two live transactions cannot both enter the route's critical section.

        Connection A takes the EXACT lock the router opens its critical section
        with -- ``get_value(source, for_update=True)`` -- and holds it (uncommitted).
        Connection B, standing in for a concurrent ``route_payment``, then tries the
        same lock with ``wait=False`` and is rejected with ``QueryTimeoutError``:
        proof the InnoDB row lock genuinely serializes the two routes, so the second
        can never reach the create/submit while the first holds the row. This is real
        cross-transaction lock contention, not a sequential re-call.
        """
        pr = self._approved_request()
        frappe.db.commit()

        with self.primary_connection():
            locked = frappe.db.get_value(SOURCE_DOCTYPE, pr.name, "name", for_update=True)
            self.assertEqual(locked, pr.name)

            with self.secondary_connection(), self.assertRaises(frappe.QueryTimeoutError):
                frappe.db.get_value(
                    SOURCE_DOCTYPE, pr.name, "name", for_update=True, wait=False
                )

            with self.primary_connection():
                first = route_payment(pr.name)
                frappe.db.commit()

        self.assertTrue(frappe.db.exists(STUB_DOCTYPE, first))
        self.addCleanup(self._cleanup_target, first)

    @timeout(15, "Concurrent route did not merge onto the committed payment")
    def test_loser_connection_merges_onto_committed_payment(self):
        """A second route in its OWN transaction merges, creating no duplicate.

        Connection A runs the full ``route_payment`` and commits -- the winner:
        exactly one submitted target, the source stamped. Connection B then runs
        ``route_payment`` on the same source in a separate transaction; it acquires
        the lock (now free), re-reads the committed ``linked_payment_entry`` and
        returns the SAME payment -- no second doc, no second (double) GL post. This
        is the serialized loser's path across two real connections.
        """
        pr = self._approved_request()

        with self.primary_connection():
            first = route_payment(pr.name)
            frappe.db.commit()

        self.assertTrue(frappe.db.exists(STUB_DOCTYPE, first))
        first_doc = frappe.get_doc(STUB_DOCTYPE, first)
        self.assertEqual(first_doc.docstatus, 1, "winning route must submit the target")
        targets_after_winner = frappe.db.count(STUB_DOCTYPE)

        with self.secondary_connection():
            second = route_payment(pr.name)
            frappe.db.commit()

        self.assertEqual(second, first, "loser route must return the winner's payment")
        self.assertEqual(
            frappe.db.count(STUB_DOCTYPE),
            targets_after_winner,
            "loser route must NOT create a second payment / second ledger post",
        )
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, first)
        self.addCleanup(self._cleanup_target, first)

    @timeout(15, "The router did not hold an exclusive lock on the source row")
    def test_route_in_progress_blocks_a_concurrent_writer(self):
        """While a route runs (lock held, uncommitted), a concurrent writer is blocked.

        Connection A runs ``route_payment`` to completion but does NOT commit -- so
        it still holds the ``for_update`` lock on the source row. Connection B's
        attempt to lock that exact row with ``wait=False`` is rejected
        (``QueryTimeoutError``): proof the lock the router takes is real and
        exclusive for the whole critical section, not a no-op. A then commits.
        """
        pr = self._approved_request()
        frappe.db.commit()

        with self.primary_connection():
            first = route_payment(pr.name)

            with self.secondary_connection(), self.assertRaises(frappe.QueryTimeoutError):
                frappe.db.get_value(
                    SOURCE_DOCTYPE, pr.name, "name", for_update=True, wait=False
                )

            with self.primary_connection():
                frappe.db.commit()

        self.assertTrue(frappe.db.exists(STUB_DOCTYPE, first))
        self.addCleanup(self._cleanup_target, first)

    def _cleanup_target(self, name):
        """Unlink the source, then cancel+delete the committed target (own tx).

        The stamp has to be cleared FIRST, and that is the router's typed link doing
        its job: the payment is now genuinely discoverable from the request that
        authorised it, so ``cancel`` runs ``check_if_doc_is_dynamically_linked``
        (frappe/model/document.py:1299-1306) and refuses while a SUBMITTED request
        still points at this target (model/delete_doc.py:350,366-371). Clearing it
        also stops a committed row outliving the throwaway DocType and breaking a
        later module's saves.
        """
        for source in frappe.get_all(
            SOURCE_DOCTYPE, filters={LINK_NAME_FIELD: name}, pluck="name"
        ):
            frappe.db.set_value(
                SOURCE_DOCTYPE,
                source,
                {LINK_DOCTYPE_FIELD: None, LINK_NAME_FIELD: None},
                update_modified=False,
            )
        if frappe.db.exists(STUB_DOCTYPE, name):
            doc = frappe.get_doc(STUB_DOCTYPE, name)
            if doc.docstatus == 1:
                doc.cancel()
            frappe.delete_doc(STUB_DOCTYPE, name, force=1, ignore_permissions=True)
        frappe.db.commit()
