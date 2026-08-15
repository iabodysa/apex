# Copyright (c) 2026, AFMCO and contributors
"""One Driver Attendance row per driver per day.

The sibling ``test_driver_attendance.py`` grades the worked-hours span. This module
grades the other half of the record's meaning: a second row for the same driver on the
same date is refused, so a day's headcount cannot be inflated by a repeated write.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_test_driver as _ensure_test_driver


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
