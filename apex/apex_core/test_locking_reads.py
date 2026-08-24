# Copyright (c) 2026, afmcoltd


import ast
import inspect

from frappe.tests.utils import FrappeTestCase

from apex.apex_core.payment_router import route_payment
from apex.habitat.doctype.resident_request.resident_request import (
    apply_bulk_triage,
    bulk_triage_job_id,
    bulk_triage,
)
from apex.salis.api.boarding import get_or_create_log
from apex.salis.api.masar import get_or_create_trip_log


def _calls_with_for_update(func, doctype_literal):
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

    def test_the_request_is_loaded_for_update(self):
        self.assertTrue(_calls_with_for_update(route_payment, "SOURCE_DOCTYPE"))

    def test_no_locking_read_is_discarded(self):
        self.assertEqual(_discarded_locking_read(route_payment), [])


class TestTripStartLogIsCreatedOnce(FrappeTestCase):

    def test_masar_locks_the_trip_before_the_existence_read(self):
        self.assertTrue(_calls_with_for_update(get_or_create_trip_log, "Dispatch Trip"))

    def test_masar_existence_read_is_itself_locking(self):
        self.assertTrue(_calls_with_for_update(get_or_create_trip_log, "Trip Start Log"))

    def test_boarding_locks_the_trip_before_the_existence_read(self):
        self.assertTrue(_calls_with_for_update(get_or_create_log, "Dispatch Trip"))

    def test_boarding_existence_read_is_itself_locking(self):
        self.assertTrue(_calls_with_for_update(get_or_create_log, "Trip Start Log"))

    def test_each_takes_its_own_lock_and_not_the_callers(self):
        for func in (get_or_create_trip_log, get_or_create_log):
            with self.subTest(func=func.__name__):
                self.assertIn("for_update", inspect.getsource(func))


class TestBulkTriageIsNotAppliedTwice(FrappeTestCase):

    def test_each_row_is_loaded_for_update(self):
        self.assertTrue(_calls_with_for_update(apply_bulk_triage, "Resident Request"))

    def test_the_background_job_is_deduplicated(self):
        source = inspect.getsource(bulk_triage)
        self.assertIn("deduplicate=True", source)
        self.assertIn("job_id=", source)

    def test_the_job_id_is_stable_for_one_selection(self):
        self.assertEqual(
            bulk_triage_job_id(["RR-1", "RR-2"]),
            bulk_triage_job_id(["RR-2", "RR-1"]),
        )

    def test_a_different_selection_is_a_different_job(self):
        self.assertNotEqual(
            bulk_triage_job_id(["RR-1", "RR-2"]),
            bulk_triage_job_id(["RR-1", "RR-3"]),
        )

    def test_an_empty_selection_still_yields_an_id(self):
        self.assertTrue(bulk_triage_job_id([]))
        self.assertTrue(bulk_triage_job_id(None))
