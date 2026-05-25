"""Wash Platform controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class WashPlatform(Document):
    def validate(self):
        if self.platform_name:
            self.platform_name = self.platform_name.strip()
        if not self.platform_name:
            frappe.throw(_("Platform Name is required."))
