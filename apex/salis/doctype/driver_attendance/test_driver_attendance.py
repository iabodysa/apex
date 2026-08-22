# Copyright (c) 2026, afmcoltd
"""What a Driver Attendance guarantees, asserted against the DocType itself.

One live attendance row per driver per day: a second row for the same driver
and date is refused, but only while the first stays live — a cancelled row
frees the day for a fresh one. ``worked_hours`` is always recomputed from
``check_in``/``check_out``, rolling to the next day when checkout precedes
check-in.

Two isolation notes this file works around, both because ``FrappeTestCase``
rolls back only once, at class teardown (``frappe/tests/utils.py:46``), never
between test methods in the same class:

* ``test_records.json``'s own rows are already standing in the database before
  any test method runs (the runner makes the subject DocType's fixtures too,
  not only its dependencies) — record 0 IS a live "DRV-000001 on 2026-01-10"
  row, so the duplicate-refusal test needs no row of its own to collide with.
* Every test that inserts a document not meant to collide with that standing
  fixture uses its own driver/date pair, distinct from the fixture's and from
  every other test in this class.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Driver"]


class TestDriverAttendance(FrappeTestCase):
    def test_a_second_live_row_for_the_same_driver_and_date_is_refused(self):
        """Two live attendance rows for one driver on one day would double the headcount."""
        duplicate = frappe.copy_doc(frappe.get_test_records("Driver Attendance")[0])
        self.assertRaisesRegex(
            frappe.ValidationError,
            "already exists",
            duplicate.insert,
        )

    def test_cancelling_the_first_row_frees_the_day_for_a_new_one(self):
        """The guard excludes cancelled rows on purpose, so a corrected day is not locked forever."""
        standing_name = frappe.db.get_value(
            "Driver Attendance",
            {"driver": "DRV-000001", "attendance_date": "2026-01-10", "docstatus": ["<", 2]},
        )
        standing = frappe.get_doc("Driver Attendance", standing_name)
        standing.submit()
        standing.cancel()

        second = frappe.copy_doc(frappe.get_test_records("Driver Attendance")[0])
        second.insert()
        self.assertTrue(second.name)

    def test_worked_hours_is_computed_from_check_in_to_check_out(self):
        """The headcount ledger reports actual worked hours, not a placeholder."""
        attendance = frappe.copy_doc(frappe.get_test_records("Driver Attendance")[0])
        attendance.attendance_date = "2026-03-01"
        attendance.check_in = "08:00:00"
        attendance.check_out = "17:00:00"
        attendance.insert()
        self.assertEqual(attendance.worked_hours, 9)

    def test_worked_hours_rolls_to_the_next_day_when_checkout_precedes_checkin(self):
        """A night-shift driver whose checkout clock time is earlier must not report negative hours."""
        attendance = frappe.copy_doc(frappe.get_test_records("Driver Attendance")[0])
        attendance.attendance_date = "2026-03-02"
        attendance.check_in = "22:00:00"
        attendance.check_out = "06:00:00"
        attendance.insert()
        self.assertEqual(attendance.worked_hours, 8)
