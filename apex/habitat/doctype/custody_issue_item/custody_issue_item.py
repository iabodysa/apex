# Copyright (c) 2026, AFMCO and contributors
"""Custody Issue Item child table controller."""

from __future__ import annotations

from frappe.model.document import Document


class CustodyIssueItem(Document):
    def before_save(self):
        # [#tgyggb]
        if not self.doctype:
            return
