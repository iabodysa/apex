"""Vehicle Category controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class VehicleCategory(Document):
    def validate(self):
        if self.category_name:
            self.category_name = self.category_name.strip()
        if not self.category_name:
            frappe.throw(_("Category Name is required."))
