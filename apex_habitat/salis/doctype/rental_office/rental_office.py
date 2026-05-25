"""Rental Office controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class RentalOffice(Document):
    def validate(self):
        if self.office_name:
            self.office_name = self.office_name.strip()
        if not self.office_name:
            frappe.throw(_("Office Name is required."))
