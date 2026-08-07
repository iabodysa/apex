# Copyright (c) 2026, afmcoltd
"""Custody Damage Item child table controller."""

from __future__ import annotations

from frappe.model.document import Document


class CustodyDamageItem(Document):
    def before_save(self):
        """Returns immediately without validating any fields on the child row."""
        if not self.doctype:
            return
