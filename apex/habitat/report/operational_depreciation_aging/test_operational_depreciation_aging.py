# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Operational Depreciation Aging register's pure classification rules.

``health_state`` and ``depreciation_pct`` decide, from an article's original cost and
current book value, which of four states it is in and how far it has written off;
``status_label`` renders that stable key to display text. These are pure functions
(no bench needed to exercise the branches), so the tests hit every state boundary
directly rather than through ``execute()``'s DB aggregation.
"""

from __future__ import annotations

import unittest

from apex.habitat.report.operational_depreciation_aging.operational_depreciation_aging import (
    DATA_ERROR,
    FULLY_DEPRECIATED,
    HEALTHY,
    OVER_BUDGET,
    depreciation_pct,
    health_state,
    status_label,
)


class TestOperationalDepreciationAging(unittest.TestCase):
    def test_positive_book_value_is_healthy(self):
        self.assertEqual(health_state(1000, 400), HEALTHY)

    def test_zero_book_value_is_fully_depreciated(self):
        self.assertEqual(health_state(1000, 0), FULLY_DEPRECIATED)

    def test_negative_book_value_is_over_budget(self):
        self.assertEqual(health_state(1000, -50), OVER_BUDGET)

    def test_zero_original_cost_with_a_book_value_is_a_data_error(self):
        """An article that cost nothing cannot legitimately carry a book value."""
        self.assertEqual(health_state(0, 100), DATA_ERROR)

    def test_zero_original_cost_and_zero_book_value_is_not_a_data_error(self):
        """Both zero is a legitimately-free, fully-depreciated article, not corrupt data."""
        self.assertEqual(health_state(0, 0), FULLY_DEPRECIATED)

    def test_depreciation_pct_is_the_written_off_share(self):
        self.assertAlmostEqual(depreciation_pct(1000, 400), 60.0)

    def test_depreciation_pct_is_capped_at_100(self):
        """A book value driven below zero must not report over 100% written off."""
        self.assertEqual(depreciation_pct(1000, -500), 100.0)

    def test_depreciation_pct_of_zero_original_cost_is_zero_not_a_division_error(self):
        self.assertEqual(depreciation_pct(0, 0), 0.0)

    def test_status_label_maps_every_state_to_distinct_text(self):
        labels = {
            status_label(HEALTHY),
            status_label(FULLY_DEPRECIATED),
            status_label(OVER_BUDGET),
            status_label(DATA_ERROR),
        }
        self.assertEqual(len(labels), 4, "each state must render to its own label")

    def test_status_label_falls_back_to_data_error_text_for_an_unknown_key(self):
        self.assertEqual(status_label("not-a-real-state"), status_label(DATA_ERROR))


if __name__ == "__main__":
    unittest.main()
