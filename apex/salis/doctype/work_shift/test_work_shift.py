# Copyright (c) 2026, afmcoltd
"""What a Work Shift guarantees, asserted against the DocType itself.

A duplicate day-of-week row is silently dropped rather than kept twice. At
least one applicable day is required. Start and end time cannot be equal (a
shift with no duration).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = []


class TestWorkShift(FrappeTestCase):
    def test_a_duplicate_day_row_is_dropped_rather_than_kept_twice(self):
        """The same weekday appearing twice must not double the shift's applicable days."""
        shift = frappe.copy_doc(frappe.get_test_records("Work Shift")[0])
        shift.append("applicable_days", {"day_of_week": "Monday"})
        shift.insert()
        days = [row.day_of_week for row in shift.applicable_days]
        self.assertEqual(days.count("Monday"), 1)

    def test_a_shift_with_no_applicable_days_is_refused(self):
        """A shift nobody works on any day of the week describes no real shift."""
        shift = frappe.copy_doc(frappe.get_test_records("Work Shift")[0])
        shift.applicable_days = []
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Select at least one applicable day",
            shift.insert,
        )

    def test_an_equal_start_and_end_time_is_refused(self):
        """A shift with no duration is not a shift."""
        shift = frappe.copy_doc(frappe.get_test_records("Work Shift")[0])
        shift.start_time = "08:00:00"
        shift.end_time = "08:00:00"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Start Time and End Time cannot be the same",
            shift.insert,
        )
