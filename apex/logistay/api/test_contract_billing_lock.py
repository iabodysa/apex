# Copyright (c) 2026, AFMCO and contributors
"""The billing duplicate check must BE the locking read, not a read beside it.

Both create actions promise duplicate-safety "serialized by a row lock". Taking the
lock is not enough. MariaDB runs at REPEATABLE READ, so a plain read issued after the
lock is still answered from the read view the transaction opened at its FIRST read —
back in ``_load_eligible_contract``. The loser of a race therefore saw a contract with
no billing row for the period, raised a second financial draft, and then wiped the
winner's row, because a child-table ``save`` deletes every stored row missing from the
in-memory document (frappe/model/document.py:471-496).

``frappe.get_doc(..., for_update=True)`` is the primitive that closes it: ``for_update``
goes into ``flags`` (document.py:123-125) and ``load_from_db`` then reads the parent
(document.py:170) AND the ``billing_documents`` children (document.py:202) with
``FOR UPDATE``. A locking read is a current read, so the decision is taken on what the
database holds now.

Site-free: the module's ``frappe`` is swapped for a stub that models exactly that split
— a non-locking read returns the opening SNAPSHOT, a ``for_update`` read returns what is
COMMITTED. The interleaving under test is the one the lock exists for: the winner's
billing row lands after this caller's read view was opened.
"""

import contextlib
import datetime
import types
import unittest
from unittest.mock import patch

import frappe

from apex.logistay.api import contract_billing


def setUpModule():
    """Both actions are ``@frappe.whitelist``ed, and that decorator's argument-type
    check reads ``frappe.local.flags`` — which only ``frappe.init`` normally sets.
    Supply it when it is absent so these cases stay site-free; leave the bench's own
    flags alone when the suite runs them on a real site."""
    if getattr(frappe.local, "flags", None) is None:
        frappe.local.flags = frappe._dict()


CONTRACT = contract_billing.CONTRACT_DOCTYPE
PURCHASE_REQUEST = contract_billing.PURCHASE_REQUEST_DOCTYPE
PAYMENT_ENTRY = contract_billing.PAYMENT_ENTRY_DOCTYPE

_PERIOD = "2026-07"
_CONTRACT_NAME = "TEL-CTR-2026-00001"
_WINNER_REQUEST = "MAT-MR-2026-00007"
_WINNER_PAYMENT = "ACC-PAY-2026-00007"


class _Thrown(Exception):
    """What the module's own ``frappe.throw`` refusal looks like to these cases."""


class _Row:
    def __init__(self, billing_period, document_type, document_name):
        self.billing_period = billing_period
        self.document_type = document_type
        self.document_name = document_name


class _Contract:
    """One Telecom Contract as ONE read of it saw it."""

    def __init__(self, rows):
        self.doctype = CONTRACT
        self.name = _CONTRACT_NAME
        self.docstatus = 1
        self.company = "_T Telecom Co"
        self.supplier = "_T Operator"
        self.service_item = "_T Telecom Service"
        self.cost_center = None
        self.project = None
        self.currency = "SAR"
        self.recurring_amount = 250
        self.billing_documents = list(rows)
        self.flags = types.SimpleNamespace()
        self.saves = 0

    def check_permission(self, permtype="read", permlevel=None):
        pass

    def reload(self):
        """A non-locking re-read. REPEATABLE READ answers it from the same read view,
        so the rows this object was built with come back unchanged — which is why a
        reload after the lock cannot decide anything."""
        return self

    def append(self, fieldname, value):
        row = _Row(value["billing_period"], value["document_type"], value["document_name"])
        getattr(self, fieldname).append(row)
        return row

    def save(self, **kwargs):
        self.saves += 1


class _NewDoc:
    def __init__(self, doctype):
        self.doctype = doctype
        self.name = None
        self.items = []

    def append(self, fieldname, value):
        getattr(self, fieldname).append(value)

    def set_missing_values(self):
        pass

    def insert(self, **kwargs):
        self.name = f"NEW-{self.doctype}"


class _StubDB:
    def __init__(self, present):
        self.present = present

    def exists(self, doctype, filters=None):
        name = filters["name"] if isinstance(filters, dict) else filters
        return name if name in self.present.get(doctype, set()) else None

    def get_value(self, doctype, filters=None, fieldname="name", **kwargs):
        return "Nos"


class _StubFrappe:
    """A transaction at REPEATABLE READ: plain reads see the snapshot, locking reads
    see what is committed."""

    def __init__(self, snapshot, committed, present):
        self.snapshot = snapshot
        self.committed = committed
        self.db = _StubDB(present)
        self.reads = []
        self.created = []
        self.utils = types.SimpleNamespace(
            now_datetime=lambda: datetime.datetime(2026, 7, 31, 12, 0, 0)
        )

    def get_doc(self, doctype, name=None, for_update=None):
        self.reads.append((doctype, name, bool(for_update)))
        return self.committed if for_update else self.snapshot

    def new_doc(self, doctype):
        doc = _NewDoc(doctype)
        self.created.append(doc)
        return doc

    def throw(self, message, **kwargs):
        raise _Thrown(message)


def _race(document_type=None, winner_name=None):
    """Two callers, one contract, one period.

    The winner committed its billing row AFTER this caller's read view was opened, so
    the snapshot carries no row for the period and the database does. Called with no
    arguments there is no winner and the period is genuinely free.
    """
    rows = [_Row(_PERIOD, document_type, winner_name)] if winner_name else []
    present = {CONTRACT: {_CONTRACT_NAME}}
    if winner_name:
        present[document_type] = {winner_name}
    return _StubFrappe(_Contract([]), _Contract(rows), present)


def _no_payable(*args, **kwargs):
    """Past the duplicate check, ``create_payment_entry`` needs a real payable invoice.
    These cases stop there — they are about the check, not about the payment."""
    raise _Thrown("no payable invoice")


@contextlib.contextmanager
def _running(stub):
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(contract_billing, "frappe", stub))
        stack.enter_context(patch.object(contract_billing, "_", lambda text: text))
        stack.enter_context(patch.object(contract_billing, "today", lambda: "2026-07-15"))
        stack.enter_context(
            patch.object(
                contract_billing,
                "payable_allocation",
                types.SimpleNamespace(
                    require_target=lambda doctype: None,
                    build_allocated_payment=_no_payable,
                ),
            )
        )
        yield


class TestTheDuplicateCheckReadsUnderTheLock(unittest.TestCase):
    def test_a_concurrent_purchase_request_is_returned_not_duplicated(self):
        stub = _race(PURCHASE_REQUEST, _WINNER_REQUEST)
        with _running(stub):
            result = contract_billing.create_purchase_request(_CONTRACT_NAME, _PERIOD)

        self.assertEqual(
            result,
            {
                "document_type": PURCHASE_REQUEST,
                "document_name": _WINNER_REQUEST,
                "existing": True,
            },
        )
        self.assertEqual(stub.created, [], "no second Material Request may be raised")
        self.assertEqual(
            (stub.snapshot.saves, stub.committed.saves),
            (0, 0),
            "no save, so the winner's billing row is not deleted",
        )

    def test_a_concurrent_payment_entry_is_returned_not_duplicated(self):
        stub = _race(PAYMENT_ENTRY, _WINNER_PAYMENT)
        with _running(stub):
            result = contract_billing.create_payment_entry(_CONTRACT_NAME, _PERIOD)

        self.assertEqual(
            result,
            {
                "document_type": PAYMENT_ENTRY,
                "document_name": _WINNER_PAYMENT,
                "existing": True,
            },
        )
        self.assertEqual(stub.created, [], "no second draft payment may be raised")
        self.assertEqual((stub.snapshot.saves, stub.committed.saves), (0, 0))

    def test_the_deciding_read_is_the_locking_one(self):
        """Eligibility is read without a lock; the duplicate check re-reads under one.

        The order is the property: a locking read taken BEFORE the check is what makes
        the check a current read, and the checked document must be the one it returned.
        """
        for action in (
            contract_billing.create_purchase_request,
            contract_billing.create_payment_entry,
        ):
            with self.subTest(action=action.__name__):
                stub = _race()
                with _running(stub), contextlib.suppress(_Thrown):
                    action(_CONTRACT_NAME, _PERIOD)
                self.assertEqual(
                    stub.reads,
                    [(CONTRACT, _CONTRACT_NAME, False), (CONTRACT, _CONTRACT_NAME, True)],
                )

    def test_a_free_period_still_raises_its_draft(self):
        """The other direction: the guard must not answer "existing" to everything."""
        stub = _race()
        with _running(stub):
            result = contract_billing.create_purchase_request(_CONTRACT_NAME, _PERIOD)

        self.assertFalse(result["existing"])
        self.assertEqual(len(stub.created), 1)
        self.assertEqual(result["document_name"], stub.created[0].name)
        self.assertEqual(
            [(r.billing_period, r.document_type) for r in stub.committed.billing_documents],
            [(_PERIOD, PURCHASE_REQUEST)],
            "the log is written onto the document the lock returned",
        )
        self.assertEqual(stub.committed.saves, 1)


if __name__ == "__main__":
    unittest.main()
