# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Driver Attendance worked-hours computation.

The rider is the shipped fixture. Attendance is unique per (driver, date), so each case
drops the row it wrote before the next one claims the same day.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today
from apex.tests.factories import make_test_driver as _ensure_test_driver

DRIVER_NAME = "_Test Driver"

class TestDriverAttendanceHours(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.driver = frappe.db.get_value("Salis Driver", {"full_name": DRIVER_NAME}, "name")

    def _attendance(self, check_in, check_out):
        doc = frappe.get_doc(
            {
                "doctype": "Driver Attendance",
                "driver": self.driver,
                "attendance_date": today(),
                "check_in": check_in,
                "check_out": check_out,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(doc.delete, ignore_permissions=True)
        return doc

    def test_overnight_shift_computes_real_span(self):
        doc = self._attendance("22:00:00", "06:00:00")
        self.assertEqual(doc.worked_hours, 8.0)

    def test_same_day_shift_still_correct(self):
        doc = self._attendance("08:00:00", "16:30:00")
        self.assertEqual(doc.worked_hours, 8.5)

test_dependencies = ['Salis Driver']

class TestDriverAttendanceUniqueness(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.driver = _ensure_test_driver()

    def _attendance(self, date):
        doc = frappe.get_doc(
            {
                "doctype": "Driver Attendance",
                "driver": self.driver,
                "attendance_date": date,
                "status": "Present",
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc,
            "Driver Attendance",
            doc.name,
            ignore_permissions=True,
            force=True,
        )
        return doc

    def test_a_second_row_for_the_same_driver_and_day_is_refused(self):
        day = frappe.utils.add_days(frappe.utils.today(), -400)
        frappe.db.delete("Driver Attendance", {"driver": self.driver, "attendance_date": day})

        self._attendance(day)

        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {
                    "doctype": "Driver Attendance",
                    "driver": self.driver,
                    "attendance_date": day,
                    "status": "Present",
                }
            ).insert(ignore_permissions=True)

    def test_the_same_driver_on_another_day_is_accepted(self):
        """Non-vacuity control: the refusal above is the date pairing, not the driver."""
        day = frappe.utils.add_days(frappe.utils.today(), -401)
        frappe.db.delete("Driver Attendance", {"driver": self.driver, "attendance_date": day})

        self.assertTrue(self._attendance(day).name)
