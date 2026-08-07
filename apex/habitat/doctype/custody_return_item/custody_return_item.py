# Copyright (c) 2026, afmcoltd
"""Custody Return Item child table controller."""

from __future__ import annotations

from frappe.model.document import Document


class CustodyReturnItem(Document):
    def before_save(self):
        """Returns immediately when the row has no doctype set and otherwise performs no action."""
        if not self.doctype:
            return
