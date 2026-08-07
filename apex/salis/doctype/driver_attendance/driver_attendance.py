# Copyright (c) 2026, afmcoltd
"""Driver Attendance controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_datetime, time_diff_in_seconds


class DriverAttendance(Document):
    def validate(self):
        """Blocks a duplicate same-day attendance row and recomputes the worked hours."""
        self._guard_duplicate()
        self._compute_worked_hours()

    def _guard_duplicate(self):
        """One attendance row per driver per day (defends the portal get-or-create
        against a concurrent double-insert)."""
        if not self.is_new():
            return
        if frappe.db.exists(
            "Driver Attendance",
            {
                "driver": self.driver,
                "attendance_date": self.attendance_date,
                "docstatus": ["<", 2],
                "name": ["!=", self.name or ""],
            },
        ):
            frappe.throw(
                _("Attendance for {0} on {1} already exists.").format(
                    self.driver, self.attendance_date
                )
            )

    def _compute_worked_hours(self):
        """Computes worked hours from check-in to check-out, rolling to next day if checkout precedes it."""
        if self.check_in and self.check_out:
            check_in = get_datetime(f"{self.attendance_date} {self.check_in}")
            check_out = get_datetime(f"{self.attendance_date} {self.check_out}")
            if check_out < check_in:
                check_out = get_datetime(f"{add_days(self.attendance_date, 1)} {self.check_out}")
            seconds = time_diff_in_seconds(check_out, check_in)
            self.worked_hours = round(seconds / 3600, 2) if seconds > 0 else 0
        else:
            self.worked_hours = 0
