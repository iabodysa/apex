"""Accommodation Bed controller. Smallest atomic spatial unit."""

from __future__ import annotations

from frappe.model.document import Document


class AccommodationBed(Document):
    def before_save(self):
        # Validate document properties
        if not self.doctype:
            return
