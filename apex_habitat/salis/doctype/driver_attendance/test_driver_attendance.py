# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Driver Attendance worked-hours computation."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today


class TestDriverAttendanceHours(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.driver = (
            frappe.get_doc(
                {
                    "doctype": "Salis Driver",
                    "full_name": f"Rider {frappe.generate_hash(length=6)}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _attendance(self, check_in, check_out):
        return frappe.get_doc(
            {
                "doctype": "Driver Attendance",
                "driver": self.driver,
                "attendance_date": today(),
                "check_in": check_in,
                "check_out": check_out,
            }
        ).insert(ignore_permissions=True)

    def test_overnight_shift_computes_real_span(self):
        # Check-in 22:00, check-out 06:00 next morning = an 8-hour night shift.
        # The old single-date math gave a negative span -> worked_hours 0.
        doc = self._attendance("22:00:00", "06:00:00")
        self.assertEqual(doc.worked_hours, 8.0)

    def test_same_day_shift_still_correct(self):
        # Non-vacuous: a daytime shift is unchanged by the overnight fix.
        doc = self._attendance("08:00:00", "16:30:00")
        self.assertEqual(doc.worked_hours, 8.5)
