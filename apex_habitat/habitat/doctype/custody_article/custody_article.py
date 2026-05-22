"""Custody Article controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class CustodyArticle(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Custody Article":
            frappe.throw("DocType mismatch")
