# Copyright (c) 2026, AFMCO and contributors
"""Routed-payment creation is serialized so a source authorization yields
EXACTLY ONE payment and EXACTLY ONE ledger post.

Background
----------
``apex_core.payment_router.route_payment`` row-locks the source request before
the idempotency check, create, submit, and link-stamp, so the whole sequence is
one critical section::

    apex/apex_core/payment_router.py:125
        frappe.db.get_value(SOURCE_DOCTYPE, payment_request, "name", for_update=True)
    apex/apex_core/payment_router.py:138
        if source.linked_payment_entry:
            return source.linked_payment_entry   # the re-read-under-lock guard

Without that lock + re-read-under-lock guard, two concurrent ``create_routed_payment``
calls for one finance-approved request could both read ``linked_payment_entry`` as
empty and both build a payment -- a double-pay, and on the auto-submit path a DOUBLE
GL post (the native target posts its ledger from its own ``on_submit``). The lock
serialises the two routes to exactly one payment; the loser re-reads the stamped
``linked_payment_entry`` and returns the existing payment instead of a second one.

What this test asserts -- and what it does NOT
----------------------------------------------
A real ``SELECT ... FOR UPDATE`` race needs two live InnoDB transactions, which Python
threads sharing one ``FrappeTestCase`` transaction cannot create, so this test does NOT
assert a literal thread race. It asserts the INVARIANT the lock guarantees,
deterministically: the duplicate guard INSIDE the critical section. It creates the
routed payment once, then drives a SECOND ``route_payment`` on the same -- now
already-paid / link-stamped -- source, and asserts the second call:

  * returns the SAME payment name (the re-read-under-lock guard fired),
  * creates NO new payment document, and
  * leaves EXACTLY ONE submitted (ledger-posting) target for that source.

This exercises the same ``if source.linked_payment_entry: return`` branch a serialized
loser takes once the winner stamps the link, on the submittable + auto-submit + GL-on
path that is the actual double-GL hazard (``test_idempotent_second_call_returns_same``
covers only the non-submitting Note target, leaving the ledger-post leg otherwise
untested). The ``for_update`` lock's structural presence is guarded separately by
``test_routed_payment_lock_source_present`` below. Fixtures are self-contained and keyed off
``self._testMethodName`` so concurrent runs never collide on a shared source row.
"""

from __future__ import annotations

import ast
import os

import apex
import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import submit_via_workflow

from apex.apex_core.payment_router import (
    LINK_DOCTYPE_FIELD,
    LINK_NAME_FIELD,
    SOURCE_DOCTYPE,
    route_payment,
)
from apex.tests._helpers import set_gl_posting

SETTINGS = "Payment Routing Settings"
FIELD_MAP_CHILD = "Payment Routing Field Map"
STUB_DOCTYPE = "Test Routed Serialization Stub"

# Resolved from the INSTALLED package. A path derived from this test's own location points
# into .claude/tests/, which holds only tests, so the read raised and the assertion below
# graded nothing.
PAYMENT_ROUTER_SOURCE = os.path.join(
    os.path.dirname(os.path.abspath(apex.__file__)), "apex_core", "payment_router.py"
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
        # Drop the pointer BEFORE the stub DocType: leaving it behind gives the single
        # a dangling Link, and _validate_links then aborts every later save of it. The
        # rows go with it — a map naming stub fieldnames is validated against the
        # default Payment Request once the target is cleared, and refused there.
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
        set_gl_posting(True)

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
        # submit_via_workflow lands the sanctioned finance-approved submit state
        # (docstatus 1) past the workflow's finance-approval guard; stamp the approver
        # the router reads.
        submit_via_workflow(doc)
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

        first = route_payment(pr.name)
        self.assertTrue(frappe.db.exists(STUB_DOCTYPE, first))
        first_doc = frappe.get_doc(STUB_DOCTYPE, first)
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
        # Stamp BOTH halves, the way a real winner leaves the row: the link
        # is a Dynamic Link, so a name without its companion doctype is a state the
        # router itself can never produce and would be refused on the next save.
        sentinel = "SENTINEL-EXISTING-PAYMENT"
        pr.db_set(
            {LINK_DOCTYPE_FIELD: STUB_DOCTYPE, LINK_NAME_FIELD: sentinel},
            update_modified=False,
        )
        pr.reload()
        self.assertEqual(pr.linked_payment_entry, sentinel)
        self.assertEqual(pr.linked_payment_doctype, STUB_DOCTYPE)

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
        ``route_payment``.

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
        # Key this to the STAMP CALL, not to a literal fieldname. The stamp
        # now writes both halves of the Dynamic Link through module constants, and a
        # guard spelled '"linked_payment_entry"' failed on that refactor while the
        # invariant it exists to protect was never touched.
        lock_pos = func_source.find("for_update=True")
        stamp_pos = func_source.find("db_set")
        self.assertGreater(stamp_pos, -1, "the link stamp was not found in route_payment")
        self.assertGreater(
            stamp_pos,
            lock_pos,
            "the link stamp must be written AFTER the for_update lock, or the "
            "duplicate check is not race-protected.",
        )
        # Both halves in that one stamp: a name written without its companion doctype
        # lets the source claim a payment type it did not create.
        self.assertIn("LINK_DOCTYPE_FIELD", func_source)
        self.assertIn("LINK_NAME_FIELD", func_source)
