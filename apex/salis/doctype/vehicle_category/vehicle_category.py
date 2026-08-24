# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from frappe.model.document import Document


class VehicleCategory(Document):
    def validate(self):
        if self.category_name:
            self.category_name = self.category_name.strip()
