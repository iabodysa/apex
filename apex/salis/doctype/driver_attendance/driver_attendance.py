# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import time_diff_in_seconds


class DriverAttendance(Document):
    def validate(self):
        self._guard_duplicate()
        self._compute_worked_hours()

    def _guard_duplicate(self):
        if not self.is_new():
            return
        frappe.db.get_value("Salis Driver", self.driver, "name", for_update=True)
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
        if not (self.check_in and self.check_out):
            self.worked_hours = 0
            return
        seconds = time_diff_in_seconds(self.check_out, self.check_in)
        if seconds < 0:
            frappe.throw(_("Check-out is earlier than check-in."))
        self.worked_hours = round(seconds / 3600, 2)
