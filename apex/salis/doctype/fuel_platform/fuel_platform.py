# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from frappe.model.document import Document


class FuelPlatform(Document):
    def validate(self):
        if self.platform_name:
            self.platform_name = self.platform_name.strip()
