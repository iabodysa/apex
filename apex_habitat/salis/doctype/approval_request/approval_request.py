"""Approval Request controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class ApprovalRequest(Document):
    def validate(self):
        if self.decision in ("Approved", "Rejected") and not self.decision_date:
            self.decision_date = now_datetime()
        if self.decision == "Pending":
            self.decision_date = None
