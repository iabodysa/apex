# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for the shared interval-overlap helper.

Behaviour contract (R2 dedup, Finding F): ``has_overlapping_record`` must return
the SAME result as the two original inline predicates it replaced — the Lease
building-scoped guard and the Utility Bill Entry company+building+account guard —
across overlap / no-overlap / adjacent / cancelled / different-scope / same-record
cases. The logic itself is pure — ``frappe.db.get_value`` is patched with an in-memory
evaluator and nothing is written.

This file is site-bound, not site-free: ``patch.object(date_ranges.frappe.db, ...)``
dereferences the werkzeug LocalProxy at patch time, so every case errors with
``RuntimeError: object is not bound`` without a connected site. ``test_report_helpers.py:88``
shows the site-free form instead (``patch.object(frappe, "db", SimpleNamespace(...))``).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from apex.apex_core.utils import date_ranges


def _match(row: dict, filters: dict) -> bool:
    """Evaluate a Frappe-style filter dict against one in-memory row."""
    for field, cond in filters.items():
        val = row.get(field)
        if isinstance(cond, (list, tuple)):
            op, target = cond
            if op == "<=" and not (val <= target):
                return False
            if op == ">=" and not (val >= target):
                return False
            if op == "!=" and not (val != target):
                return False
            if op == "=" and not (val == target):
                return False
        elif val != cond:
            return False
    return True


def _query(rows, filters):
    """First matching row's name, or None — stands in for frappe.db.get_value."""
    for row in rows:
        if _match(row, filters):
            return row["name"]
    return None


# Lease scenario table
# New lease under test: building B1, name "NEW", spanning the dates set in the dict below.
_NEW_LEASE = {
    "building": "B1",
    "lease_start_date": "2026-03-01",
    "lease_end_date": "2026-06-30",
    "name": "NEW",
}
_LEASE_ROWS = [
    # overlapping, active
    {"name": "L1", "building": "B1", "docstatus": 1,
     "lease_start_date": "2026-05-01", "lease_end_date": "2026-08-01"},
    # starts the day after new ends -> no overlap
    {"name": "L2", "building": "B1", "docstatus": 1,
     "lease_start_date": "2026-07-01", "lease_end_date": "2026-09-01"},
    # adjacent-touching (existing.start == new.end) -> inclusive overlap
    {"name": "L3", "building": "B1", "docstatus": 1,
     "lease_start_date": "2026-06-30", "lease_end_date": "2026-08-01"},
    # overlapping but a different building -> out of scope
    {"name": "L4", "building": "B2", "docstatus": 1,
     "lease_start_date": "2026-04-01", "lease_end_date": "2026-05-01"},
    # overlapping but cancelled -> excluded
    {"name": "L5", "building": "B1", "docstatus": 2,
     "lease_start_date": "2026-04-01", "lease_end_date": "2026-05-01"},
]


def _old_lease_filter(doc):
    return {
        "building": doc["building"],
        "docstatus": ["!=", 2],
        "name": ["!=", doc["name"] or ""],
        "lease_start_date": ["<=", doc["lease_end_date"]],
        "lease_end_date": [">=", doc["lease_start_date"]],
    }


# Utility Bill Entry scenario table
# New bill under test: company C1, building B1, account A1, name "NEW", billing period
# spanning the dates set in the dict below.
_NEW_UTIL = {
    "company": "C1", "building": "B1", "utility_account": "A1",
    "billing_period_from": "2026-03-01", "billing_period_to": "2026-03-31",
    "name": "NEW",
}
_UTIL_ROWS = [
    # overlapping, same scope, active
    {"name": "U1", "company": "C1", "building": "B1", "utility_account": "A1",
     "docstatus": 1, "billing_period_from": "2026-03-15", "billing_period_to": "2026-04-15"},
    # no overlap (period after)
    {"name": "U2", "company": "C1", "building": "B1", "utility_account": "A1",
     "docstatus": 1, "billing_period_from": "2026-04-01", "billing_period_to": "2026-04-30"},
    # overlapping but different company -> out of scope (proves multi-key scope)
    {"name": "U3", "company": "C2", "building": "B1", "utility_account": "A1",
     "docstatus": 1, "billing_period_from": "2026-03-10", "billing_period_to": "2026-03-20"},
    # overlapping but different utility account -> out of scope
    {"name": "U4", "company": "C1", "building": "B1", "utility_account": "A2",
     "docstatus": 1, "billing_period_from": "2026-03-10", "billing_period_to": "2026-03-20"},
    # overlapping but cancelled -> excluded
    {"name": "U5", "company": "C1", "building": "B1", "utility_account": "A1",
     "docstatus": 2, "billing_period_from": "2026-03-10", "billing_period_to": "2026-03-20"},
]


def _old_util_filter(doc):
    return {
        "company": doc["company"],
        "building": doc["building"],
        "utility_account": doc["utility_account"],
        "billing_period_from": ["<=", doc["billing_period_to"]],
        "billing_period_to": [">=", doc["billing_period_from"]],
        "docstatus": ["!=", 2],
        "name": ["!=", doc["name"] or ""],
    }


class TestHasOverlappingRecord(unittest.TestCase):
    def _call(self, rows, *args, **kwargs):
        with patch.object(
            date_ranges.frappe.db, "get_value",
            side_effect=lambda dt, filters, field: _query(rows, filters),
        ):
            return date_ranges.has_overlapping_record(*args, **kwargs)

    # Two subTest tables below cover what would otherwise be ten separate methods — six for
    # Lease, four for Utility Bill Entry — each making the SAME call with a different `rows`
    # slice, keeping every distinct value including the `exclude_name=None` input. The legacy
    # oracle applies uniformly, since every arm calls with exactly _NEW_LEASE's / _NEW_UTIL's
    # own field values, so the two tables run it exhaustively. Collapsing is safe here: plain
    # unittest.TestCase, in-memory rows, frappe.db.get_value patched per call, nothing
    # written, session user never changed.
    def test_the_lease_guard_answers_exactly_as_the_predicate_it_replaced(self):
        same_record = {"name": "NEW", "building": "B1", "docstatus": 0,
                       "lease_start_date": "2026-04-01", "lease_end_date": "2026-05-01"}
        for label, rows, expected in (
            ("an active overlap is found (L1 precedes the adjacent L3)", _LEASE_ROWS, "L1"),
            ("a lease starting the day after new ends", [_LEASE_ROWS[1]], None),
            ("adjacent-touching is an inclusive overlap", [_LEASE_ROWS[2]], "L3"),
            ("an overlap in another building is out of scope", [_LEASE_ROWS[3]], None),
            ("a cancelled overlap is excluded", [_LEASE_ROWS[4]], None),
            ("the row being saved never conflicts with itself", [same_record], None),
        ):
            with self.subTest(case=label):
                new = self._call(
                    rows, "Lease", {"building": _NEW_LEASE["building"]},
                    "lease_start_date", "lease_end_date",
                    _NEW_LEASE["lease_start_date"], _NEW_LEASE["lease_end_date"],
                    _NEW_LEASE["name"],
                )
                self.assertEqual(new, expected)
                self.assertEqual(
                    new,
                    _query(rows, _old_lease_filter(_NEW_LEASE)),
                    "the shared helper disagreed with the inline predicate it replaced",
                )

    def test_the_utility_guard_answers_exactly_as_the_predicate_it_replaced(self):
        scope = {"company": "C1", "building": "B1", "utility_account": "A1"}
        for label, rows, exclude_name, expected in (
            ("an in-scope overlap is found", _UTIL_ROWS, _NEW_UTIL["name"], "U1"),
            # Different company and different utility account, both overlapping in time.
            ("scope isolates company and account", [_UTIL_ROWS[2], _UTIL_ROWS[3]], "NEW", None),
            ("a cancelled overlap is excluded", [_UTIL_ROWS[4]], "NEW", None),
            # exclude_name=None must not crash and must exclude nothing real.
            ("no exclude_name still finds the overlap", [_UTIL_ROWS[0]], None, "U1"),
        ):
            with self.subTest(case=label):
                new = self._call(
                    rows, "Utility Bill Entry", scope,
                    "billing_period_from", "billing_period_to",
                    _NEW_UTIL["billing_period_from"], _NEW_UTIL["billing_period_to"],
                    exclude_name,
                )
                self.assertEqual(new, expected)
                self.assertEqual(
                    new,
                    _query(rows, _old_util_filter(_NEW_UTIL)),
                    "the shared helper disagreed with the inline predicate it replaced",
                )


if __name__ == "__main__":
    unittest.main()
