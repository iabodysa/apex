# Copyright (c) 2026, afmcoltd
from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_time


class WorkShift(Document):
    def validate(self):
        self._deduplicate_days()
        if not self.applicable_days:
            frappe.throw(_("Select at least one applicable day."))
        if get_time(self.start_time) == get_time(self.end_time):
            frappe.throw(_("Start Time and End Time cannot be the same."))

    def _deduplicate_days(self):
        seen = set()
        for row in list(self.applicable_days or []):
            if not row.day_of_week or row.day_of_week in seen:
                self.remove(row)
                continue
            seen.add(row.day_of_week)
