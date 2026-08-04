# Copyright (c) 2026, AFMCO and contributors
"""Custody Return Item child table controller."""

from __future__ import annotations

from frappe.model.document import Document


class CustodyReturnItem(Document):
    def before_save(self):
        if not self.doctype:
            return
