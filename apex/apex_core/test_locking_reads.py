# Copyright (c) 2026, afmcoltd

"""A locking read whose result is discarded protects nothing.

The shape these tests guard: ``frappe.db.get_value(..., for_update=True)`` taken for its
side effect, then a plain ``frappe.get_doc`` that answers from the transaction's own
snapshot — taken BEFORE the lock. Under MariaDB's REPEATABLE READ the second caller sees
the pre-lock world and acts on it. The lock works, nothing times out, no exception is
raised, and both callers report success, which is why this cannot be found by watching a
run fail.

Each test reads the SOURCE of the path it guards rather than racing two real callers: a
race that has to be provoked is a race that passes when the machine is fast, and the
property here — the lock and the read are one statement — is exact and readable.
"""

import ast
import inspect

from frappe.tests.utils import FrappeTestCase


def _calls_with_for_update(func, doctype_literal):
    """True when the function loads ``doctype_literal`` with ``for_update`` set."""
    tree = ast.parse(inspect.getsource(func))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        source = ast.unparse(node)
        if doctype_literal not in source:
            continue
        if any(kw.arg == "for_update" for kw in node.keywords):
            return True
    return False


def _discarded_locking_read(func):
    """Statements that call for_update and throw the answer away."""
    tree = ast.parse(inspect.getsource(func))
    return [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and any(kw.arg == "for_update" for kw in node.value.keywords)
        and "Dispatch Trip" not in ast.unparse(node.value)
    ]


class TestPaymentRouterLocksWhatItReads(FrappeTestCase):
    """A second caller must not pay one request twice."""

    def test_the_request_is_loaded_for_update(self):
        from apex.apex_core.payment_router import route_payment

        self.assertTrue(_calls_with_for_update(route_payment, "SOURCE_DOCTYPE"))

    def test_no_locking_read_is_discarded(self):
        from apex.apex_core.payment_router import route_payment

        self.assertEqual(_discarded_locking_read(route_payment), [])


class TestTripStartLogIsCreatedOnce(FrappeTestCase):
    """A driver scan and a worker self-confirm can arrive together."""

    def test_masar_locks_the_trip_before_the_existence_read(self):
        from apex.salis.api.masar import _get_or_create_trip_log

        self.assertTrue(_calls_with_for_update(_get_or_create_trip_log, "Dispatch Trip"))

    def test_masar_existence_read_is_itself_locking(self):
        from apex.salis.api.masar import _get_or_create_trip_log

        self.assertTrue(_calls_with_for_update(_get_or_create_trip_log, "Trip Start Log"))

    def test_boarding_locks_the_trip_before_the_existence_read(self):
        from apex.salis.api.boarding import _get_or_create_log

        self.assertTrue(_calls_with_for_update(_get_or_create_log, "Dispatch Trip"))

    def test_boarding_existence_read_is_itself_locking(self):
        from apex.salis.api.boarding import _get_or_create_log

        self.assertTrue(_calls_with_for_update(_get_or_create_log, "Trip Start Log"))

    def test_each_takes_its_own_lock_and_not_the_callers(self):
        """The lock lives inside the function, so a new caller cannot forget it."""
        from apex.salis.api.boarding import _get_or_create_log
        from apex.salis.api.masar import _get_or_create_trip_log

        for func in (_get_or_create_trip_log, _get_or_create_log):
            with self.subTest(func=func.__name__):
                self.assertIn("for_update", inspect.getsource(func))


class TestBulkTriageIsNotAppliedTwice(FrappeTestCase):
    """A double-click must not advance the same rows through two workers."""

    def test_each_row_is_loaded_for_update(self):
        from apex.habitat.doctype.resident_request.resident_request import (
            _apply_bulk_triage,
        )

        self.assertTrue(_calls_with_for_update(_apply_bulk_triage, "Resident Request"))

    def test_the_background_job_is_deduplicated(self):
        from apex.habitat.doctype.resident_request.resident_request import bulk_triage

        source = inspect.getsource(bulk_triage)
        self.assertIn("deduplicate=True", source)
        self.assertIn("job_id=", source)

    def test_the_job_id_is_stable_for_one_selection(self):
        from apex.habitat.doctype.resident_request.resident_request import (
            _bulk_triage_job_id,
        )

        self.assertEqual(
            _bulk_triage_job_id(["RR-1", "RR-2"]),
            _bulk_triage_job_id(["RR-2", "RR-1"]),
        )

    def test_a_different_selection_is_a_different_job(self):
        from apex.habitat.doctype.resident_request.resident_request import (
            _bulk_triage_job_id,
        )

        self.assertNotEqual(
            _bulk_triage_job_id(["RR-1", "RR-2"]),
            _bulk_triage_job_id(["RR-1", "RR-3"]),
        )

    def test_an_empty_selection_still_yields_an_id(self):
        """``deduplicate`` throws without a job_id, so this must never be blank."""
        from apex.habitat.doctype.resident_request.resident_request import (
            _bulk_triage_job_id,
        )

        self.assertTrue(_bulk_triage_job_id([]))
        self.assertTrue(_bulk_triage_job_id(None))
