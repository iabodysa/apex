# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Driver Attendance worked-hours computation.

The rider is the shipped fixture. Attendance is unique per (driver, date), so each case
drops the row it wrote before the next one claims the same day.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

test_dependencies = ["Salis Driver"]

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
