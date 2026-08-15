"""The weekly window must follow the site's own first day of the week.

Python's `weekday()` is Monday-based. Frappe reads System Settings `first_day_of_the_week`
and defaults to Sunday (`frappe/utils/data.py:69-70`), so code that hardcodes Monday is a day
out on any site keeping the default. The error is invisible mid-week and only shows on the
boundary day, which is why reading the code did not catch it.
"""

import datetime
import unittest

import frappe
from frappe.utils import get_first_day_of_week, get_last_day_of_week, getdate


class TestWeekBoundaryFollowsSystemSettings(unittest.TestCase):
    def setUp(self):
        self.original = frappe.db.get_single_value("System Settings", "first_day_of_the_week")
        self.addCleanup(self._restore)

    def _restore(self):
        frappe.db.set_single_value("System Settings", "first_day_of_the_week", self.original)
        frappe.clear_cache()

    def _set_week_start(self, day):
        frappe.db.set_single_value("System Settings", "first_day_of_the_week", day)
        frappe.clear_cache()

    def test_the_native_window_moves_with_the_setting_and_the_hardcoded_one_does_not(self):
        """A Sunday is the boundary: it belongs to a different week under each setting."""
        sunday = getdate("2026-08-02")
        self.assertEqual(sunday.weekday(), 6, "the fixture date must be a Sunday")

        self._set_week_start("Monday")
        monday_start = get_first_day_of_week(sunday)

        self._set_week_start("Sunday")
        sunday_start = get_first_day_of_week(sunday)

        self.assertNotEqual(
            monday_start, sunday_start,
            "the two settings must disagree on this date, or the fixture proves nothing",
        )
        self.assertEqual(sunday_start, sunday, "a Sunday starts its own week when the site says so")
        self.assertEqual(monday_start, sunday - datetime.timedelta(days=6))

        hardcoded = sunday - datetime.timedelta(days=sunday.weekday())
        self.assertEqual(hardcoded, monday_start)
        self.assertNotEqual(
            hardcoded, sunday_start,
            "this is the defect: the old expression cannot follow the setting",
        )

    def test_the_coverage_gate_window_follows_the_setting(self):
        """weekly_safety_coverage_gate reaches the same verdict under either setting, because
        it now asks frappe for the window instead of assuming Monday."""
        from apex.habitat.tasks import safety

        source = safety.weekly_safety_coverage_gate.__code__.co_names
        self.assertIn("get_first_day_of_week", source)
        self.assertIn("get_last_day_of_week", source)
        self.assertNotIn(
            "weekday", source,
            "a Monday-based weekday() call is what made the gate disagree with the site",
        )

        for day in ("Sunday", "Monday"):
            self._set_week_start(day)
            today_date = getdate("2026-08-02")
            start, end = get_first_day_of_week(today_date), get_last_day_of_week(today_date)
            self.assertLessEqual(start, today_date)
            self.assertGreaterEqual(end, today_date)
            self.assertEqual((end - start).days, 6, f"{day}: a week is seven days")

    def test_the_scheduled_task_period_key_follows_the_setting(self):
        """The Weekly due_date key is the week start, so it must move with the setting too."""
        from apex.habitat.tasks import scheduled_tasks

        outer = scheduled_tasks.daily_scheduled_task_instance_generator.__code__
        inner = [c for c in outer.co_consts
                 if hasattr(c, "co_name") and c.co_name == "_period_key"]
        self.assertEqual(len(inner), 1, "the period-key helper must still be there to grade")
        # The import lives in the enclosing function, so the helper reaches it as a FREE
        # variable rather than a global — co_names alone reports only ('str','month','replace').
        names = set(inner[0].co_names) | set(inner[0].co_freevars)
        self.assertIn("get_first_day_of_week", names)
        self.assertNotIn("timedelta", names, "the hardcoded Monday offset is gone")
