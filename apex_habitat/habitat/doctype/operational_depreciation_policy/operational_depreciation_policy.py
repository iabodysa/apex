"""Operational Depreciation Policy controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class OperationalDepreciationPolicy(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Operational Depreciation Policy":
            frappe.throw("DocType mismatch")
