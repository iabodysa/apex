from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWorkShift(FrappeTestCase):
    def _shift(self, *, start_time="20:00:00", end_time="05:00:00", days=None):
        return frappe.get_doc(
            {
                "doctype": "Work Shift",
                "shift_name": "Night",
                "start_time": start_time,
                "end_time": end_time,
                "applicable_days": days or [],
            }
        )

    def test_overnight_shift_is_valid_and_duplicate_days_are_removed(self):
        shift = self._shift(
            days=[
                {"day_of_week": "Monday"},
                {"day_of_week": "Monday"},
                {"day_of_week": "Tuesday"},
            ]
        )

        shift.validate()

        self.assertEqual(
            [row.day_of_week for row in shift.applicable_days],
            ["Monday", "Tuesday"],
        )

    def test_shift_requires_at_least_one_day(self):
        shift = self._shift(days=[])

        with self.assertRaises(frappe.ValidationError):
            shift.validate()

    def test_shift_rejects_equal_start_and_end_times(self):
        shift = self._shift(
            start_time="08:00:00",
            end_time="08:00:00",
            days=[{"day_of_week": "Sunday"}],
        )

        with self.assertRaises(frappe.ValidationError):
            shift.validate()
