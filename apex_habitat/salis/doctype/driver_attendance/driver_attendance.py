"""Driver Attendance controller."""

from __future__ import annotations

from frappe.model.document import Document
from frappe.utils import get_datetime, time_diff_in_seconds


class DriverAttendance(Document):
    def validate(self):
        self._compute_worked_hours()

    def _compute_worked_hours(self):
        if self.check_in and self.check_out:
            check_in = get_datetime(f"{self.attendance_date} {self.check_in}")
            check_out = get_datetime(f"{self.attendance_date} {self.check_out}")
            seconds = time_diff_in_seconds(check_out, check_in)
            self.worked_hours = round(seconds / 3600, 2) if seconds > 0 else 0
        else:
            self.worked_hours = 0
