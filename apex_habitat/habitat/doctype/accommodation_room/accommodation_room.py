"""Accommodation Room controller."""

from __future__ import annotations

from frappe.model.document import Document


class AccommodationRoom(Document):
    def before_save(self):
        # Validate document properties
        if not self.doctype:
            return
