# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for logistay.utils.billing.monthly_equivalent.

Pure arithmetic (frappe.utils.flt only, no DB / live site), so a plain
unittest TestCase that exercises each frequency branch directly.
"""

from __future__ import annotations

import unittest

from apex.logistay.utils.billing import monthly_equivalent


class TestMonthlyEquivalent(unittest.TestCase):
    def test_quarterly_divides_by_three(self):
        self.assertEqual(monthly_equivalent(300, "Quarterly"), 100.0)

    def test_annually_divides_by_twelve(self):
        self.assertEqual(monthly_equivalent(1200, "Annually"), 100.0)

    def test_monthly_and_unknown_frequency_pass_through(self):
        self.assertEqual(monthly_equivalent(100, "Monthly"), 100.0)
        self.assertEqual(monthly_equivalent(100, None), 100.0)
        self.assertEqual(monthly_equivalent(100, "Weekly"), 100.0)

    def test_none_amount_coerces_to_zero(self):
        self.assertEqual(monthly_equivalent(None, "Quarterly"), 0.0)

    def test_string_amount_is_coerced(self):
        self.assertEqual(monthly_equivalent("300", "Quarterly"), 100.0)


if __name__ == "__main__":
    unittest.main()
