# Copyright (c) 2026, AFMCO and contributors
"""Datetime-boundary test for the Salis alert dedupe window (R10).

``_raise_alert`` suppresses a duplicate Open alert of the same type for the same
vehicle/driver "today". ``raised_on`` is a Datetime column that keeps
microseconds, so the old ``["between", [f"{today()} 00:00:00", f"{today()}
23:59:59"]]`` upper bound silently missed a row stamped 23:59:59.xxxxxx — the
dedupe then reopened the very duplicate it was meant to suppress. The window now
derives both bounds from ONE today() call and uses a next-day-midnight upper
bound that includes the whole final second.

Pure-logic test: ``frappe.db.exists`` is patched to capture the dedupe filter and
short-circuit (so no Operations Alert row is inserted), exercising the boundary
deterministically without a live bench.
"""

from __future__ import annotations

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from apex.salis import tasks


class TestAlertDedupeBoundary(FrappeTestCase):
    def test_dedupe_window_excludes_2359_upper_bound(self):
        # RED before R10: upper bound was "<today> 23:59:59" (misses .xxxxxx rows).
        # GREEN: upper bound is next-day midnight from a single today() call.
        from frappe.utils import add_days, today

        captured = {}

        def _fake_exists(doctype, filters):
            captured["filters"] = filters
            return True  # treat as "duplicate exists" -> _raise_alert returns None

        with patch(
            "apex.salis.tasks.common.frappe.db.exists", side_effect=_fake_exists
        ):
            result = tasks._raise_alert("License Expiry", "Warning", "msg", driver="DRV-X")

        self.assertIsNone(result)  # dedupe short-circuited
        window = captured["filters"]["raised_on"]
        self.assertEqual(window[0], "between")
        lower, upper = window[1]
        self.assertEqual(lower, f"{today()} 00:00:00")
        # Upper bound is next-day midnight, NOT "<today> 23:59:59".
        self.assertEqual(upper, f"{add_days(today(), 1)} 00:00:00")
        self.assertNotIn("23:59:59", upper)

    def test_dedupe_window_uses_single_today_call(self):
        # Both bounds share the same date prefix (no split-today() midnight straddle).
        from frappe.utils import add_days, today

        captured = {}

        def _fake_exists(doctype, filters):
            captured["filters"] = filters
            return True

        with patch(
            "apex.salis.tasks.common.frappe.db.exists", side_effect=_fake_exists
        ):
            tasks._raise_alert("License Expiry", "Warning", "msg", vehicle="VEH-X")

        lower, upper = captured["filters"]["raised_on"][1]
        self.assertTrue(lower.startswith(today()))
        self.assertTrue(upper.startswith(add_days(today(), 1)))
