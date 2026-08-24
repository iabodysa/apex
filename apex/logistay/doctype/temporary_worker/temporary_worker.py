# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days

DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 90


class TemporaryWorker(Document):
    def validate(self) -> None:
        self._validate_window_days()
        self._compute_expiry_date()

    def _validate_window_days(self) -> None:
        if not self.window_days:
            self.window_days = DEFAULT_WINDOW_DAYS
        if self.window_days < 1:
            frappe.throw(_("Window Days must be at least 1 day."))
        if self.window_days > MAX_WINDOW_DAYS:
            frappe.throw(
                _("Window Days cannot exceed {0} days.").format(MAX_WINDOW_DAYS)
            )

    def _compute_expiry_date(self) -> None:
        if self.arrival_date:
            self.expiry_date = add_days(self.arrival_date, self.window_days)
