# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _work_shift(**overrides):
    fields = {
        "doctype": "Work Shift",
        "shift_name": "_T-WorkShift " + frappe.generate_hash(length=6),
        "start_time": "07:00:00",
        "end_time": "16:00:00",
        "applicable_days": [{"day_of_week": "Sunday"}, {"day_of_week": "Monday"}],
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestWorkShiftApplicableDays(FrappeTestCase):
    def test_a_shift_with_no_applicable_day_is_refused(self):
        doc = _work_shift(applicable_days=[])
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_a_repeated_day_is_dropped_before_the_row_is_stored(self):
        doc = _work_shift(applicable_days=[
            {"day_of_week": "Sunday"},
            {"day_of_week": "Sunday"},
            {"day_of_week": "Monday"},
        ]).insert(ignore_permissions=True)
        self.assertEqual([row.day_of_week for row in doc.applicable_days],
                         ["Sunday", "Monday"])

    def test_a_row_naming_no_day_is_dropped(self):
        doc = _work_shift(applicable_days=[
            {"day_of_week": "Sunday"},
            {"day_of_week": ""},
        ]).insert(ignore_permissions=True)
        self.assertEqual([row.day_of_week for row in doc.applicable_days], ["Sunday"])


class TestWorkShiftWindow(FrappeTestCase):
    def test_a_shift_starting_and_ending_at_the_same_time_is_refused(self):
        doc = _work_shift(start_time="07:00:00", end_time="07:00:00")
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_a_shift_that_crosses_midnight_is_accepted(self):
        doc = _work_shift(start_time="22:00:00", end_time="06:00:00")
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.doctype, "Work Shift")
