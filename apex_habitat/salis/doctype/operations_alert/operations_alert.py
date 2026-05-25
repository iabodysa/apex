"""Operations Alert controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class OperationsAlert(Document):
    def before_insert(self):
        if not self.raised_on:
            self.raised_on = now_datetime()
