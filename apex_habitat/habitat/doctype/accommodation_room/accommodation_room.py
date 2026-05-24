"""Accommodation Room controller."""

from __future__ import annotations

from frappe.model.document import Document


class AccommodationRoom(Document):
    pass


def before_save(doc, method=None):
    # Validate document properties
    if not doc.doctype:
        return
