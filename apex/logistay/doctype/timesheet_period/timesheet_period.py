# Copyright (c) 2026, AFMCO and contributors
"""Timesheet Period controller.

One billing / attendance cycle a Timesheet Line and Timesheet Ledger row belong
to. Uniqueness is guaranteed by ``period_label`` being the record id. The one
real invariant is the window: the period cannot end before it starts.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class TimesheetPeriod(Document):
    def validate(self) -> None:
        self._validate_window()

    def _validate_window(self) -> None:
        if self.start_date and self.end_date and getdate(self.start_date) > getdate(
            self.end_date
        ):
            frappe.throw(_("Start Date cannot be after End Date."))
