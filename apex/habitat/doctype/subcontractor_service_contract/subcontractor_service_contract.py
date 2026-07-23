# Copyright (c) 2026, AFMCO and contributors
"""Subcontractor Service Contract controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class SubcontractorServiceContract(Document):
    def validate(self):
        if self.contract_start_date and self.contract_end_date:
            if getdate(self.contract_end_date) < getdate(self.contract_start_date):
                frappe.throw(_("Contract End cannot be before Contract Start."))
