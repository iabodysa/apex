# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class BoardingScanLog(Document):
    def before_insert(self):
        if not self.scanned_at:
            self.scanned_at = frappe.utils.now_datetime()

    def on_update(self):
        if not self.is_new() and not self.flags.in_insert:
            frappe.throw(_("Boarding Scan Log rows are append-only and cannot be edited."))
