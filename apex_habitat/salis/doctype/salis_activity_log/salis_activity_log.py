"""Activity Log controller.

Server-written audit trail. Entries are created by server-side document
events or controlled APIs, never trusted from the browser.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class SalisActivityLog(Document):
    def before_insert(self):
        if not self.logged_at:
            self.logged_at = now_datetime()
        if not self.user:
            self.user = frappe.session.user
