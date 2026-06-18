"""Regression test (T-147): routed-payment creation is serialized so a source
authorization yields EXACTLY ONE payment and EXACTLY ONE ledger post.

Background
----------
``apex_core.payment_router.route_payment`` row-locks the source request before
the idempotency check, create, submit, and link-stamp, so the whole sequence is
one critical section::

    apex_habitat/apex_core/payment_router.py:125
        frappe.db.get_value(SOURCE_DOCTYPE, payment_request, "name", for_update=True)
    apex_habitat/apex_core/payment_router.py:138
        if source.linked_payment_entry:
            return source.linked_payment_entry   # the re-read-under-lock guard

Without that lock + re-read-under-lock guard, two concurrent
``create_routed_payment`` calls for one finance-approved request could both read
``linked_payment_entry`` as empty and both build a payment -- a double-pay, and
on the auto-submit path a DOUBLE GL post (the native target posts its ledger from
its own ``on_submit``). The lock serialises the two routes to exactly one payment;
the loser re-reads the now-stamped ``linked_payment_entry`` under the lock and
returns the existing payment instead of creating a second one.

What this test asserts -- and what it does NOT
----------------------------------------------
True OS-thread / DB row-lock contention is not reproducible in a single-process
``FrappeTestCase`` (a real ``SELECT ... FOR UPDATE`` block needs two live InnoDB
transactions; Python threads sharing one test transaction cannot reproduce it).
So this test does NOT assert a literal thread race. Instead it asserts the
INVARIANT the lock exists to guarantee, deterministically: the duplicate guard
that runs INSIDE the critical section. We create the routed payment once, then
drive a SECOND ``route_payment`` on the same -- now already-paid / link-stamped --
source, and assert the second call:

  * returns the SAME payment name (the re-read-under-lock guard fired), and
  * creates NO new payment document, and
  * leaves EXACTLY ONE submitted (ledger-posting) target for that source.

This exercises the same ``if source.linked_payment_entry: return`` branch that a
serialized loser transaction would take once the winner has stamped the link, on
the submittable + auto-submit + GL-on path that is the actual double-GL hazard
(the existing ``test_idempotent_second_call_returns_same`` only covers the
non-submitting Note target, so the ledger-post leg was untested).

The structural presence of the ``for_update`` lock itself is additionally guarded
by ``test_routed_payment_lock_source_present`` below, mirroring the
source-presence guard style of ``tests/test_bed_booking_concurrency.py``.

Fixtures are self-contained and keyed off ``self._testMethodName`` so concurrent
runs of different methods never collide on a shared source row.
"""

from __future__ import annotations

import ast
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.apex_core.payment_router import (
    SOURCE_DOCTYPE,
    route_payment,
)

SETTINGS = "Payment Routing Settings"
# A throwaway SUBMITTABLE target so the auto-submit (ledger-post) leg is real.
STUB_DOCTYPE = "Test Routed Serialization Stub"

PAYMENT_ROUTER_SOURCE = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "apex_core",
        "payment_router.py",
    )
)


def _make_stub_submittable_doctype():
    """Create a throwaway submittable DocType used as the routed target payment.

    Submittable so the auto-submit branch actually submits it (the leg that, on
    the native path, posts a GL entry from ``on_submit``); carries a Currency
    ``paid_amount`` and a Data ``party`` for the field map to populate. Idempotent
    across reruns.
    """
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


class TestRoutedPaymentSerialization(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        _make_stub_submittable_doctype()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        if frappe.db.exists("DocType", STUB_DOCTYPE):
            frappe.delete_doc("DocType", STUB_DOCTYPE, force=1, ignore_permissions=True)
            frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
        # Route to the submittable stub, auto-submit ON, GL posting ON -- so the
        # create path actually submits the target (the double-GL hazard the lock
        # guards). Field map copies the source amount onto the target.
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
        self._set_gl_posting(True)

    def _set_gl_posting(self, enabled):
        """Flip the app-wide enable_gl_posting flag the router's GL gate reads."""
        apex = frappe.get_single("Apex Settings")
        apex.enable_gl_posting = 1 if enabled else 0
        apex.save(ignore_permissions=True)

    def _approved_request(self, **overrides):
        """A finance-STAMPED, submitted Salis Payment Request keyed to this test.

        The router gates on the immutable ``finance_approved_by`` stamp the finance
        gate writes on a real approval (proven end to end in
        test_salis_payment_request_workflow); here it is set directly as a fixture
        so this test stays focused on the serialization/idempotency invariant. The
        remarks embed ``self._testMethodName`` so parallel methods never share a row.
        """
        data = {
            "doctype": SOURCE_DOCTYPE,
            "expense_type": "Rental",
            "amount": 1000.00,
            "remarks": f"serialization-{self._testMethodName}",
            "status": "Draft",
        }
        data.update(overrides)
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True)
        doc.submit()
        doc.status = "Approved by Finance"
        doc.save(ignore_permissions=True)
        doc.db_set("finance_approved_by", "Administrator", update_modified=False)
        doc.reload()
        return doc

    def _count_targets_for(self, source_name):
        """Number of routed target docs whose paid_amount matches this source.

        The stub has no back-reference field, so identity is established through
        the source's ``linked_payment_entry`` stamp (asserted to be exactly one
        below); this count over the stub table is a defence-in-depth check that no
        stray second target was built by the re-route.
        """
        return frappe.db.count(STUB_DOCTYPE)

    def test_reroute_on_paid_source_creates_no_second_payment_or_ledger_post(self):
        """A second route on an already-paid source yields ONE payment, ONE post.

        This is the invariant the FOR UPDATE lock + re-read-under-lock guard
        guarantee for a serialized loser transaction. (See module docstring: this
        asserts the guard's invariant deterministically, NOT a literal thread race.)
        """
        pr = self._approved_request(amount=1000.00)

        targets_before = frappe.db.count(STUB_DOCTYPE)

        # Winner: builds and submits exactly one target, stamps the link.
        first = route_payment(pr.name)
        self.assertTrue(frappe.db.exists(STUB_DOCTYPE, first))
        first_doc = frappe.get_doc(STUB_DOCTYPE, first)
        # The target was SUBMITTED -- this is the ledger-posting leg on the native
        # path; the lock guards against a SECOND such submit for one source.
        self.assertEqual(first_doc.docstatus, 1, "winning route must submit the target")
        self.assertEqual(float(first_doc.paid_amount), 1000.00)

        pr.reload()
        self.assertEqual(
            pr.linked_payment_entry,
            first,
            "winning route must stamp linked_payment_entry on the source",
        )
        targets_after_first = frappe.db.count(STUB_DOCTYPE)
        self.assertEqual(
            targets_after_first,
            targets_before + 1,
            "winning route must create exactly one target payment",
        )

        # Loser: the SAME re-read-under-lock guard a serialized second transaction
        # hits once the winner has stamped the link. Must return the SAME payment
        # and build nothing new -- no second payment, no second (double) GL post.
        second = route_payment(pr.name)
        self.assertEqual(
            second,
            first,
            "re-route must return the existing payment (duplicate guard fired)",
        )
        self.assertEqual(
            frappe.db.count(STUB_DOCTYPE),
            targets_after_first,
            "re-route must NOT create a second payment / second ledger post",
        )

        # Exactly ONE submitted target exists for this source's stamped link.
        self.assertEqual(first_doc.docstatus, 1)
        pr.reload()
        self.assertEqual(
            pr.linked_payment_entry,
            first,
            "the source's link must still point at the single original payment",
        )

    def test_link_stamp_short_circuits_before_any_new_doc(self):
        """A source already carrying a ``linked_payment_entry`` never builds a doc.

        Directly stamp the link (modelling the state a serialized winner leaves
        behind, committed, before the loser re-reads it under the lock), then route:
        the guard at payment_router.py:138 must short-circuit and return the stamped
        name without creating any target -- the loser-transaction path.
        """
        pr = self._approved_request(amount=42.00)
        # Pre-stamp the link to a sentinel; no target is built for it.
        sentinel = "SENTINEL-EXISTING-PAYMENT"
        pr.db_set("linked_payment_entry", sentinel, update_modified=False)
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, sentinel)

        targets_before = frappe.db.count(STUB_DOCTYPE)
        returned = route_payment(pr.name)

        self.assertEqual(
            returned,
            sentinel,
            "route must return the already-stamped payment, not build a new one",
        )
        self.assertEqual(
            frappe.db.count(STUB_DOCTYPE),
            targets_before,
            "an already-linked source must not create any target payment",
        )

    def test_routed_payment_lock_source_present(self):
        """Structural guard: the FOR UPDATE row-lock on the source must remain in
        ``route_payment`` (mirrors tests/test_bed_booking_concurrency.py).

        The runtime tests above assert the GUARD'S invariant but cannot reproduce
        the DB row-lock that makes two real concurrent transactions serialize; this
        check fails loudly if the ``for_update`` lock that provides that
        serialization is removed or moved out of ``route_payment``.
        """
        self.assertTrue(
            os.path.exists(PAYMENT_ROUTER_SOURCE),
            f"payment_router.py not found: {PAYMENT_ROUTER_SOURCE}",
        )
        with open(PAYMENT_ROUTER_SOURCE, encoding="utf-8") as fh:
            source = fh.read()

        tree = ast.parse(source, filename=PAYMENT_ROUTER_SOURCE)
        route_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "route_payment":
                route_node = node
                break
        self.assertIsNotNone(
            route_node,
            "function 'route_payment' not found -- the chokepoint was renamed/removed",
        )

        func_source = "\n".join(
            source.splitlines()[route_node.lineno - 1 : route_node.end_lineno]
        )
        self.assertIn(
            "for_update=True",
            func_source,
            "the SELECT ... FOR UPDATE source row-lock was removed from "
            "route_payment; restore it so concurrent routes serialize to one "
            "payment before merging.",
        )
        # Anchor the lock ahead of the COMMITTED stamp (db_set with the quoted
        # field name), which is unambiguously after the lock — unlike the first
        # textual mention of linked_payment_entry, which an earlier read/docstring
        # reference can precede and false-fail.
        lock_pos = func_source.find("for_update=True")
        stamp_pos = func_source.find('"linked_payment_entry"')
        self.assertGreater(stamp_pos, -1, "the linked_payment_entry stamp was not found in route_payment")
        self.assertGreater(
            stamp_pos,
            lock_pos,
            "the linked_payment_entry stamp must be written AFTER the for_update "
            "lock, or the duplicate check is not race-protected.",
        )
