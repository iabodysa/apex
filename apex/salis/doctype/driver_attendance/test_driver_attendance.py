# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _driver():
    return frappe.get_doc(
        {
            "doctype": "Salis Driver",
            "full_name": "_T-Attendance Driver " + frappe.generate_hash(length=6),
        }
    ).insert(ignore_permissions=True).name


def _attendance(driver, **overrides):
    fields = {
        "doctype": "Driver Attendance",
        "driver": driver,
        "attendance_date": frappe.utils.today(),
        "status": "Present",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestDriverAttendanceOneRowPerDay(FrappeTestCase):
    def test_a_second_row_for_one_driver_on_one_day_is_refused(self):
        driver = _driver()
        _attendance(driver).insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "already exists"):
            _attendance(driver).insert(ignore_permissions=True)

    def test_the_same_driver_on_the_next_day_is_accepted(self):
        driver = _driver()
        _attendance(driver).insert(ignore_permissions=True)
        doc = _attendance(
            driver, attendance_date=frappe.utils.add_days(frappe.utils.today(), 1)
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.driver, driver)


class TestDriverAttendanceWorkedHours(FrappeTestCase):
    def test_a_day_shift_is_counted_from_check_in_to_check_out(self):
        day = frappe.utils.today()
        doc = _attendance(
            _driver(), check_in=f"{day} 07:00:00", check_out=f"{day} 16:30:00"
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.worked_hours, 9.5)

    def test_a_shift_that_ends_on_the_next_day_is_counted_across_the_boundary(self):
        day = frappe.utils.today()
        doc = _attendance(
            _driver(),
            check_in=f"{day} 22:00:00",
            check_out=f"{frappe.utils.add_days(day, 1)} 06:00:00",
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.worked_hours, 8.0)

    def test_a_check_out_before_the_check_in_is_refused(self):
        day = frappe.utils.today()
        with self.assertRaisesRegex(frappe.ValidationError, "earlier than"):
            _attendance(
                _driver(), check_in=f"{day} 16:00:00", check_out=f"{day} 07:00:00"
            ).insert(ignore_permissions=True)


class TestDriverAttendanceUnreadClock(FrappeTestCase):
    def test_a_new_document_carries_no_reading_nobody_took(self):
        doc = frappe.new_doc("Driver Attendance")
        self.assertIsNone(doc.check_in)
        self.assertIsNone(doc.check_out)

    def test_a_row_without_a_reading_counts_no_hours(self):
        doc = _attendance(_driver()).insert(ignore_permissions=True)
        self.assertIsNone(doc.check_in)
        self.assertEqual(doc.worked_hours, 0)
