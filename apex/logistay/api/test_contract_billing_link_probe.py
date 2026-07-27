# Copyright (c) 2026, AFMCO and contributors
"""The billing log's existence probe must ask the database, not the string.

``_existing_link`` decides whether a period already has paperwork. It reads the
recorded ``document_name`` back through ``frappe.db.exists``, which answers the
name back WITHOUT querying when it equals the DocType (database.py:1259). A row
logging "Payment Entry" therefore reported a live draft on the strength of the
string alone, and every caller — both create actions and ``get_billing_status`` —
would have believed it.

Scope of the claim: the billing row's ``document_name`` is a Dynamic Link, and
Frappe validates those through ``frappe.db.get_value`` (base_document.py:830),
which carries no such short-circuit. A save therefore refuses the self-named pair
unless a document really bears that name, so the state is not reachable from the
UI today. These cases pin the probe's own contract instead: duplicate-safety is
what this function exists for, and it must not rest on a neighbouring layer
happening to filter the input first.

Site-free: only ``frappe.db.exists`` is exercised, so the module's ``frappe`` is
swapped for ``tests.factories.ExistsShortCircuitDB`` — the shared stub that
reproduces the short-circuit faithfully for every suite pinning this defect.
"""

import unittest
from unittest.mock import patch

from apex.logistay.api import contract_billing
from apex.tests.factories import ExistsShortCircuitDB

_PERIOD = "2026-07"


class _Row:
    def __init__(self, billing_period, document_type, document_name):
        self.billing_period = billing_period
        self.document_type = document_type
        self.document_name = document_name


class _Contract:
    def __init__(self, rows):
        self.billing_documents = rows


class _Thrown(Exception):
    """What the module's own ``frappe.throw`` refusal looks like to these cases."""


class _StubFrappe:
    def __init__(self, present):
        self.db = ExistsShortCircuitDB(present)
        self.loaded = []

    def throw(self, message, **_kwargs):
        raise _Thrown(message)

    def get_doc(self, doctype, name):
        self.loaded.append((doctype, name))
        raise AssertionError(f"the guard let {doctype} {name!r} through to get_doc")


def _run(rows, present, document_type):
    stub = _StubFrappe(present)
    with patch.object(contract_billing, "frappe", stub):
        return contract_billing._existing_link(_Contract(rows), _PERIOD, document_type), stub


class TestRecordedNameIsVerifiedAgainstTheDatabase(unittest.TestCase):
    def test_a_name_equal_to_its_doctype_is_not_taken_on_trust(self):
        found, stub = _run(
            [_Row(_PERIOD, "Payment Entry", "Payment Entry")],
            present={"Payment Entry": set()},
            document_type="Payment Entry",
        )
        self.assertIsNone(found, "an absent document must never pass as a live draft")
        self.assertTrue(stub.db.queried, "the probe must reach the database, not short-circuit")

    def test_a_document_really_bearing_that_name_is_still_returned(self):
        """The other direction: the fix must not turn duplicate-safety into a
        duplicate. A bare ``name != doctype`` rejection would raise a second draft
        here, which is the behaviour this module's contract rules out."""
        found, _ = _run(
            [_Row(_PERIOD, "Payment Entry", "Payment Entry")],
            present={"Payment Entry": {"Payment Entry"}},
            document_type="Payment Entry",
        )
        self.assertEqual(found, "Payment Entry")

    def test_an_ordinary_live_draft_is_returned(self):
        found, _ = _run(
            [_Row(_PERIOD, "Material Request", "MAT-MR-2026-00001")],
            present={"Material Request": {"MAT-MR-2026-00001"}},
            document_type="Material Request",
        )
        self.assertEqual(found, "MAT-MR-2026-00001")

    def test_a_deleted_draft_frees_the_period(self):
        found, _ = _run(
            [_Row(_PERIOD, "Material Request", "MAT-MR-2026-00001")],
            present={"Material Request": set()},
            document_type="Material Request",
        )
        self.assertIsNone(found)

    def test_another_period_or_type_is_never_matched(self):
        rows = [
            _Row("2026-06", "Material Request", "MAT-MR-2026-00001"),
            _Row(_PERIOD, "Payment Entry", "ACC-PAY-2026-00001"),
        ]
        present = {
            "Material Request": {"MAT-MR-2026-00001"},
            "Payment Entry": {"ACC-PAY-2026-00001"},
        }
        self.assertIsNone(_run(rows, present, "Material Request")[0])

    def test_a_row_with_no_recorded_name_is_skipped(self):
        found, _ = _run(
            [_Row(_PERIOD, "Material Request", None)],
            present={"Material Request": set()},
            document_type="Material Request",
        )
        self.assertIsNone(found)


class TestWhitelistedIdentifiersCannotClearTheirOwnGate(unittest.TestCase):
    """The reachable half of the same defect: both loaders take their identifier
    straight from a whitelisted endpoint, so a caller can pass the DocType name
    itself and clear an existence gate without a query. The document is still
    absent, so ``get_doc`` then raises a bare framework 404 in place of the named
    refusal each loader defines — the guard is skipped, not the permission check.
    """

    def _refuses(self, call, doctype):
        stub = _StubFrappe({doctype: set()})
        with patch.object(contract_billing, "frappe", stub), patch.object(
            contract_billing, "_", lambda text: text
        ):
            with self.assertRaises(_Thrown):
                call()
        self.assertEqual(stub.loaded, [], "the refusal must land before get_doc")

    def test_a_contract_id_equal_to_its_doctype_is_refused(self):
        self._refuses(
            lambda: contract_billing._load_eligible_contract("Telecom Contract"),
            "Telecom Contract",
        )

    def test_a_payable_id_equal_to_its_doctype_is_refused(self):
        self._refuses(
            lambda: contract_billing._load_eligible_payable(_Contract([]), "Purchase Invoice"),
            "Purchase Invoice",
        )


if __name__ == "__main__":
    unittest.main()
