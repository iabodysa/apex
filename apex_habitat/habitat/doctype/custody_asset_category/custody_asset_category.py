"""Custody Asset Category controller."""

from __future__ import annotations

from frappe.model.document import Document


class CustodyAssetCategory(Document):
    pass


def before_save(doc, method=None):
    # Validate document properties
    pass
