# Copyright (c) 2026, afmcoltd
"""Wash Platform controller."""

from __future__ import annotations

from frappe.model.document import Document


class WashPlatform(Document):
    def validate(self):
        """Trims the platform name so the stored value matches the name frappe derives from it."""
        if self.platform_name:
            self.platform_name = self.platform_name.strip()
