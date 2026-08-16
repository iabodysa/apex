# Copyright (c) 2026, AFMCO and contributors
"""Tests for the missing-attendance scheduled watch.

Asserts the docstring's contract: an Active Salis Driver with no submitted Driver
Attendance for today is queued to the Fleet Supervisor queue (via
``_queue_document``); a driver who already has one is left alone.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.salis.tasks.attendance import missing_attendance_watch


def _driver(prefix):
    return frappe.get_doc(
        {
            "doctype": "Salis Driver",
            "full_name": f"{prefix} {frappe.generate_hash(length=12)}",
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


class TestMissingAttendanceWatch(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.driver_with = _driver("MAW-With")
        self.driver_without = _driver("MAW-Without")
        self.attendance = frappe.get_doc(
            {
                "doctype": "Driver Attendance",
                "driver": self.driver_with,
                "attendance_date": today(),
            }
        ).insert(ignore_permissions=True)
        self.attendance.submit()
        self.addCleanup(self._purge)

    def _purge(self):
        frappe.set_user("Administrator")
        if frappe.db.exists("Driver Attendance", self.attendance.name):
            frappe.get_doc("Driver Attendance", self.attendance.name).cancel()
            frappe.delete_doc(
                "Driver Attendance", self.attendance.name, force=True, ignore_permissions=True
            )
        frappe.delete_doc("Salis Driver", self.driver_with, force=True, ignore_permissions=True)
        frappe.delete_doc("Salis Driver", self.driver_without, force=True, ignore_permissions=True)

    def test_driver_without_todays_attendance_is_queued(self):
        with patch("apex.salis.tasks.attendance._queue_document") as queued:
            missing_attendance_watch()

        queued_names = [
            call.args[1] for call in queued.call_args_list if call.args[0] == "Salis Driver"
        ]
        self.assertIn(self.driver_without, queued_names)
        self.assertNotIn(self.driver_with, queued_names)
