# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for the shared interval-overlap helper.

Behaviour contract (R2 dedup, Finding F): ``has_overlapping_record`` must return
the SAME result as the two original inline predicates it replaced — the Lease
building-scoped guard and the Utility Bill Entry company+building+account guard —
across overlap / no-overlap / adjacent / cancelled / different-scope / same-record
cases. These are pure-logic tests: ``frappe.db.get_value`` is patched with an
in-memory evaluator, so no site is required.
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


# --- Lease scenario table -------------------------------------------------
# New lease under test: building B1, [2026-03-01, 2026-06-30], name "NEW".
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


# --- Utility Bill Entry scenario table ------------------------------------
# New bill under test: company C1, building B1, account A1,
# billing period [2026-03-01, 2026-03-31], name "NEW".
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

    def test_lease_scope_matches_legacy(self):
        new = self._call(
            _LEASE_ROWS, "Lease", {"building": _NEW_LEASE["building"]},
            "lease_start_date", "lease_end_date",
            _NEW_LEASE["lease_start_date"], _NEW_LEASE["lease_end_date"],
            _NEW_LEASE["name"],
        )
        old = _query(_LEASE_ROWS, _old_lease_filter(_NEW_LEASE))
        self.assertEqual(new, old)
        # overlap (L1) is found first; L3 adjacent also overlaps but L1 precedes it
        self.assertEqual(new, "L1")

    def test_lease_no_overlap(self):
        rows = [_LEASE_ROWS[1]]  # only L2 (after)
        new = self._call(
            rows, "Lease", {"building": "B1"},
            "lease_start_date", "lease_end_date", "2026-03-01", "2026-06-30", "NEW",
        )
        self.assertIsNone(new)
        self.assertEqual(new, _query(rows, _old_lease_filter(_NEW_LEASE)))

    def test_lease_adjacent_is_overlap(self):
        rows = [_LEASE_ROWS[2]]  # L3 adjacent-touching
        new = self._call(
            rows, "Lease", {"building": "B1"},
            "lease_start_date", "lease_end_date", "2026-03-01", "2026-06-30", "NEW",
        )
        self.assertEqual(new, "L3")
        self.assertEqual(new, _query(rows, _old_lease_filter(_NEW_LEASE)))

    def test_lease_different_building_out_of_scope(self):
        rows = [_LEASE_ROWS[3]]  # L4 other building
        new = self._call(
            rows, "Lease", {"building": "B1"},
            "lease_start_date", "lease_end_date", "2026-03-01", "2026-06-30", "NEW",
        )
        self.assertIsNone(new)

    def test_lease_cancelled_excluded(self):
        rows = [_LEASE_ROWS[4]]  # L5 docstatus 2
        new = self._call(
            rows, "Lease", {"building": "B1"},
            "lease_start_date", "lease_end_date", "2026-03-01", "2026-06-30", "NEW",
        )
        self.assertIsNone(new)

    def test_lease_same_record_excluded(self):
        rows = [{"name": "NEW", "building": "B1", "docstatus": 0,
                 "lease_start_date": "2026-04-01", "lease_end_date": "2026-05-01"}]
        new = self._call(
            rows, "Lease", {"building": "B1"},
            "lease_start_date", "lease_end_date", "2026-03-01", "2026-06-30", "NEW",
        )
        self.assertIsNone(new, "the row being saved must never conflict with itself")

    def test_utility_scope_matches_legacy(self):
        scope = {"company": "C1", "building": "B1", "utility_account": "A1"}
        new = self._call(
            _UTIL_ROWS, "Utility Bill Entry", scope,
            "billing_period_from", "billing_period_to",
            _NEW_UTIL["billing_period_from"], _NEW_UTIL["billing_period_to"],
            _NEW_UTIL["name"],
        )
        old = _query(_UTIL_ROWS, _old_util_filter(_NEW_UTIL))
        self.assertEqual(new, old)
        self.assertEqual(new, "U1")

    def test_utility_scope_isolates_company_and_account(self):
        # Only the out-of-scope overlapping rows present -> no conflict.
        rows = [_UTIL_ROWS[2], _UTIL_ROWS[3]]  # different company, different account
        scope = {"company": "C1", "building": "B1", "utility_account": "A1"}
        new = self._call(
            rows, "Utility Bill Entry", scope,
            "billing_period_from", "billing_period_to",
            "2026-03-01", "2026-03-31", "NEW",
        )
        self.assertIsNone(new)
        self.assertEqual(new, _query(rows, _old_util_filter(_NEW_UTIL)))

    def test_utility_cancelled_excluded(self):
        rows = [_UTIL_ROWS[4]]  # U5 docstatus 2
        scope = {"company": "C1", "building": "B1", "utility_account": "A1"}
        new = self._call(
            rows, "Utility Bill Entry", scope,
            "billing_period_from", "billing_period_to",
            "2026-03-01", "2026-03-31", "NEW",
        )
        self.assertIsNone(new)

    def test_exclude_name_none_treated_as_empty(self):
        # exclude_name=None must not crash and must exclude nothing real.
        rows = [_UTIL_ROWS[0]]
        scope = {"company": "C1", "building": "B1", "utility_account": "A1"}
        new = self._call(
            rows, "Utility Bill Entry", scope,
            "billing_period_from", "billing_period_to",
            "2026-03-01", "2026-03-31", None,
        )
        self.assertEqual(new, "U1")


if __name__ == "__main__":
    unittest.main()
