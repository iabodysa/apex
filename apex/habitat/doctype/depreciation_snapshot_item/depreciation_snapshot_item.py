# Copyright (c) 2026, afmcoltd
"""Depreciation Snapshot Item child table controller."""

from __future__ import annotations

from frappe.model.document import Document


class DepreciationSnapshotItem(Document):
    def before_save(self):
        """Returns immediately without validating any fields on the child row."""
        if not self.doctype:
            return
