"""Custody Issue Item child table controller."""

from __future__ import annotations

from frappe.model.document import Document


class CustodyIssueItem(Document):
    def before_save(self):
        # [#2qfbj3]
        if not self.doctype:
            return
