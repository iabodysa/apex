# Copyright (c) 2026, afmcoltd
"""Vehicle Category controller."""

from __future__ import annotations

from frappe.model.document import Document


class VehicleCategory(Document):
    def validate(self):
        """Trims the category name so the stored value matches the name frappe derives from it."""
        if self.category_name:
            self.category_name = self.category_name.strip()
