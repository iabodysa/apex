# Copyright (c) 2026, AFMCO and contributors
"""Rental Office controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class RentalOffice(Document):
    def onload(self):
        # Wire the native Frappe Address widget (Dynamic Link, ERPNext pattern).
        from frappe.contacts.address_and_contact import load_address_and_contact

        load_address_and_contact(self)

    def validate(self):
        if self.office_name:
            self.office_name = self.office_name.strip()
        if not self.office_name:
            frappe.throw(_("Office Name is required."))
