# Copyright (c) 2026, afmcoltd

"""The weekly safety period must follow the site's own first day of the week.

``_current_period`` names the window a walker is filling; ``tasks/safety.py`` grades
the round they submit from ``get_first_day_of_week``. If the two resolve the week
differently the screen credits one period while the coverage gate counts another, and
on the site's own first day they differ by a full week rather than a day. These tests
fail against any window computed from ``date.weekday()``, which is Monday-based.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_first_day_of_week, get_last_day_of_week, getdate

from apex.habitat.api.safety_checklist import _current_period

SUNDAY = "2026-08-23"
MONDAY = "2026-08-24"
SATURDAY = "2026-08-22"


class TestCurrentPeriod(FrappeTestCase):
    """No records, no permissions — the function's own arithmetic."""

    def setUp(self):
        """Remember the site's setting so no case leaks its week start into the next.

        Every case that reads the window MUST pin the setting itself: the rollback
        restores the row, not the cache ``get_system_settings`` answers from, and a
        case inheriting a Monday start makes a Monday-based window look correct.
        """
        self._original_week_start = frappe.db.get_single_value(
            "System Settings", "first_day_of_the_week"
        )

    def tearDown(self):
        self._set_week_start(self._original_week_start or "Sunday")

    def _set_week_start(self, day):
        """Write the System Setting and drop the cache ``get_system_settings`` reads."""
        frappe.db.set_single_value("System Settings", "first_day_of_the_week", day)
        frappe.clear_cache()

    def test_weekly_window_matches_the_primitive(self):
        self._set_week_start("Sunday")
        for on_date in (SUNDAY, MONDAY, SATURDAY):
            with self.subTest(on_date=on_date):
                start, end, period = _current_period("Weekly", on_date)
                self.assertEqual(start, getdate(get_first_day_of_week(on_date)))
                self.assertEqual(end, getdate(get_last_day_of_week(on_date)))
                self.assertEqual(period, {"kind": "week"})

    def test_the_site_first_day_moves_the_window(self):
        """A Sunday-start site and a Monday-start site disagree on a Sunday."""
        self._set_week_start("Sunday")
        sunday_start, _, _ = _current_period("Weekly", SUNDAY)
        self._set_week_start("Monday")
        monday_start, _, _ = _current_period("Weekly", SUNDAY)

        self.assertEqual(sunday_start, getdate(SUNDAY))
        self.assertNotEqual(sunday_start, monday_start)
        self.assertEqual((getdate(SUNDAY) - monday_start).days, 6)

    def test_a_round_on_the_first_day_falls_inside_its_own_week(self):
        """The defect this guards: a round submitted on the site's first day was
        placed in the week that had just ended."""
        self._set_week_start("Sunday")
        start, end, _ = _current_period("Weekly", SUNDAY)
        self.assertLessEqual(start, getdate(SUNDAY))
        self.assertGreaterEqual(end, getdate(SUNDAY))

    def test_other_cadences_are_untouched(self):
        self._set_week_start("Sunday")
        day_start, day_end, day_period = _current_period("Daily", SUNDAY)
        self.assertEqual(day_start, day_end)
        self.assertEqual(day_period, {"kind": "day"})

        month_start, month_end, month_period = _current_period("Monthly", SUNDAY)
        self.assertEqual(str(month_start), "2026-08-01")
        self.assertEqual(str(month_end), "2026-08-31")
        self.assertEqual(month_period["kind"], "month")
