"""Custody Article controller."""

from __future__ import annotations

from frappe.model.document import Document


class CustodyArticle(Document):
    pass


def before_save(doc, method=None):
    # Validate document properties
    pass
