"""Custody Asset Category controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class CustodyAssetCategory(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Custody Asset Category":
            frappe.throw("DocType mismatch")
