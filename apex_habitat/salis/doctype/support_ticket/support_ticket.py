"""Support Ticket controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class SupportTicket(Document):
    def validate(self):
        for row in self.messages or []:
            if not row.sent_at:
                row.sent_at = now_datetime()
            if not row.sender:
                row.sender = frappe.session.user
