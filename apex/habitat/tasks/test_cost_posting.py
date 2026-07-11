# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for the shared accommodation-ledger posting helper.

Behaviour contract (R2 dedup, Finding D): ``_post_accommodation_ledger_row`` is
now the SINGLE writer of the daily Operational-Memo Accommodation Ledger row.
These tests pin the financial behaviour that must never drift:

  1. the inserted row is the exact 18-key literal the two callers used before;
  2. the ``employee_daily_share`` rounding equals BOTH legacy formulas (the batch
     two-step and the back-date nested form);
  3. the existence guard makes posting idempotent (no duplicate insert);
  4. the batch allocator and the back-date path post an IDENTICAL row; and
  5. the callers keep their DISTINCT duplicate-handling — the batch path swallows
     DuplicateEntryError WITHOUT logging (only rolls back) and logs other errors,
     while the back-date path logs every error under a single Exception guard.

Pure-logic tests: frappe DB access is patched, so no site is required.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from apex.habitat.tasks import cost


class _D(dict):
    """dict with attribute access, mimicking frappe._dict rows."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            return None


# Representative inputs shared across tests.
_ARGS = dict(
    posting_date="2026-03-01",
    employee="EMP-1",
    assignment="HA-1",
    building="BLD-1",
    project="PRJ-1",
    cost_center="CC-1",
    billed_to_supplier="SUP-1",
    ledger_type="Rent",
    annual_cost=36600,
    capacity=10,
    days_in_year=365,
)

# The exact row the pre-refactor code inserted (both callers, byte-identical).
# employee_daily_share = flt(flt(36600/365, 5) / 10, 5) = 10.0274.
_EXPECTED_ROW = {
    "doctype": "Accommodation Ledger",
    "posting_date": "2026-03-01",
    "employee": "EMP-1",
    "assignment": "HA-1",
    "building": "BLD-1",
    "project": "PRJ-1",
    "cost_center": "CC-1",
    "billed_to_supplier": "SUP-1",
    "ledger_type": "Rent",
    "total_site_cost": 36600,
    "capacity_denominator": 10,
    "employee_daily_share": 10.0274,
    "posting_mode": "Operational Memo",
    "source_doctype": "Housing Assignment",
    "source_name": "HA-1",
    "allocation_basis": "Capacity",
    "allocation_period_start": "2026-03-01",
    "allocation_period_end": "2026-03-01",
}


class TestPostAccommodationLedgerRow(unittest.TestCase):
    def _capture_insert(self):
        """Return (get_doc_mock, captured_list) where captured_list gets the dict
        passed to frappe.get_doc when a row is inserted."""
        captured = []

        def _get_doc(doc):
            captured.append(doc)
            m = MagicMock()
            m.insert = MagicMock()
            return m

        return _get_doc, captured

    def test_builds_exact_legacy_row(self):
        get_doc, captured = self._capture_insert()
        with patch.object(cost.frappe.db, "exists", return_value=None), \
                patch.object(cost.frappe, "get_doc", side_effect=get_doc):
            cost._post_accommodation_ledger_row(**_ARGS)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0], _EXPECTED_ROW,
                         "helper must build the identical 18-key ledger row")
        # No key added or dropped.
        self.assertEqual(set(captured[0]), set(_EXPECTED_ROW))

    def test_daily_share_matches_both_legacy_formulas(self):
        from frappe.utils import flt
        cases = [
            (36600, 365, 10),
            (100000, 366, 7),   # leap year
            (12345, 365, 3),
            (1, 365, 100),      # rounds toward tiny share
        ]
        for annual, days, cap in cases:
            get_doc, captured = self._capture_insert()
            args = dict(_ARGS, annual_cost=annual, days_in_year=days, capacity=cap)
            with patch.object(cost.frappe.db, "exists", return_value=None), \
                    patch.object(cost.frappe, "get_doc", side_effect=get_doc):
                cost._post_accommodation_ledger_row(**args)
            produced = captured[0]["employee_daily_share"]
            batch_daily_cost = flt(annual / days, 5)          # legacy batch step 1
            batch_share = flt(batch_daily_cost / cap, 5)      # legacy batch step 2
            backdate_share = flt(flt(annual / days, 5) / cap, 5)  # legacy back-date
            self.assertEqual(produced, batch_share, (annual, days, cap))
            self.assertEqual(produced, backdate_share, (annual, days, cap))

    def test_existence_guard_skips_insert(self):
        get_doc, captured = self._capture_insert()
        with patch.object(cost.frappe.db, "exists", return_value="EXISTING-ROW"), \
                patch.object(cost.frappe, "get_doc", side_effect=get_doc) as gd:
            cost._post_accommodation_ledger_row(**_ARGS)
        gd.assert_not_called()
        self.assertEqual(captured, [], "idempotent: an existing row is never re-posted")


# shared stubs for the two caller paths

def _building_doc():
    doc = MagicMock()
    doc.total_capacity = 10
    doc.get.side_effect = lambda f: 36600 if f == "annual_rent" else 0
    return doc


class TestCallerPaths(unittest.TestCase):
    """Exercise allocate_building_accommodation_cost and backdate_assignment_cost
    end to end (DB patched) to prove identical rows + distinct dup-handling."""

    def _run_batch(self, insert_side_effect=None):
        """Run the batch allocator for one building/one assignment/Rent-only.
        Returns (captured_rows, rollback_mock, log_error_mock)."""
        captured = []

        def _get_doc(*a, **k):
            if a and a[0] == "Building":
                return _building_doc()
            # dict form -> a ledger row insert
            doc = a[0]
            captured.append(doc)
            m = MagicMock()
            m.insert = MagicMock()
            return m

        assignment = _D(name="HA-1", employee="EMP-1", project="PRJ-1",
                        cost_center="CC-1", billed_to_supplier="SUP-1")

        exists = MagicMock(side_effect=lambda dt, *a, **k: dt == "Building")
        get_all = MagicMock(side_effect=[[assignment], []])
        rollback = MagicMock()
        log_error = MagicMock()
        logger = MagicMock()

        patches = [
            patch.object(cost.frappe, "get_doc", side_effect=_get_doc),
            patch.object(cost.frappe.db, "exists", exists),
            patch.object(cost.frappe, "get_all", get_all),
            patch.object(cost.frappe.db, "rollback", rollback),
            patch.object(cost.frappe, "log_error", log_error),
            patch.object(cost.frappe, "logger", return_value=logger),
            patch("apex.habitat.doctype.building.building.apply_active_lease",
                  lambda d: None),
        ]
        if insert_side_effect is not None:
            patches.append(patch.object(
                cost, "_post_accommodation_ledger_row",
                side_effect=insert_side_effect))
        with _nested(patches):
            cost.allocate_building_accommodation_cost("BLD-1", "2026-03-01")
        return captured, rollback, log_error

    def _run_backdate(self, insert_side_effect=None):
        captured = []

        def _get_doc(*a, **k):
            if a and a[0] == "Building":
                return _building_doc()
            doc = a[0]
            captured.append(doc)
            m = MagicMock()
            m.insert = MagicMock()
            return m

        asgn = _D(name="HA-1", employee="EMP-1", building="BLD-1", project="PRJ-1",
                  cost_center="CC-1", billed_to_supplier="SUP-1")

        get_value = MagicMock(return_value=asgn)
        exists = MagicMock(return_value=None)  # ledger existence check
        rollback = MagicMock()
        log_error = MagicMock()

        patches = [
            patch.object(cost.frappe, "get_doc", side_effect=_get_doc),
            patch.object(cost.frappe.db, "get_value", get_value),
            patch.object(cost.frappe.db, "exists", exists),
            patch.object(cost.frappe.db, "rollback", rollback),
            patch.object(cost.frappe, "log_error", log_error),
            patch("apex.habitat.doctype.building.building.apply_active_lease",
                  lambda d: None),
        ]
        if insert_side_effect is not None:
            patches.append(patch.object(
                cost, "_post_accommodation_ledger_row",
                side_effect=insert_side_effect))
        with _nested(patches):
            days = cost.backdate_assignment_cost("HA-1", "2026-03-01", "2026-03-01")
        return captured, rollback, log_error, days

    def test_both_paths_post_identical_row(self):
        batch_rows, _, _ = self._run_batch()
        back_rows, _, _, days = self._run_backdate()
        self.assertEqual(len(batch_rows), 1)
        self.assertEqual(len(back_rows), 1)
        self.assertEqual(days, 1)
        self.assertEqual(batch_rows[0], _EXPECTED_ROW)
        self.assertEqual(back_rows[0], _EXPECTED_ROW)
        self.assertEqual(batch_rows[0], back_rows[0],
                         "batch and back-date must post byte-identical rows")

    def test_batch_swallows_duplicate_without_logging(self):
        dup = cost.frappe.exceptions.DuplicateEntryError

        def _raise(*a, **k):
            raise dup("dup")

        _, rollback, log_error = self._run_batch(insert_side_effect=_raise)
        rollback.assert_called_once()
        log_error.assert_not_called()  # [#g4zbzv] duplicate is a benign no-op

    def test_batch_logs_other_errors(self):
        def _raise(*a, **k):
            raise ValueError("boom")

        _, rollback, log_error = self._run_batch(insert_side_effect=_raise)
        rollback.assert_called_once()
        log_error.assert_called_once()  # [#9hso8i] real failure is logged

    def test_backdate_logs_every_error_single_guard(self):
        # Distinct from batch: the back-date path has ONE except-Exception guard,
        # so even a DuplicateEntryError is rolled back AND logged.
        dup = cost.frappe.exceptions.DuplicateEntryError

        def _raise(*a, **k):
            raise dup("dup")

        _, rollback, log_error, days = self._run_backdate(insert_side_effect=_raise)
        rollback.assert_called_once()
        log_error.assert_called_once()
        self.assertEqual(days, 1)


def _nested(patchers):
    """Enter a list of patch objects as one context manager."""
    from contextlib import ExitStack
    stack = ExitStack()
    for p in patchers:
        stack.enter_context(p)
    return stack


if __name__ == "__main__":
    unittest.main()
