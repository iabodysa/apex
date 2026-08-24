# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from apex.apex_core.utils.company import resolve_company
from apex.apex_core.utils.vat import apply_vat


class SubcontractorServiceContract(Document):
    def validate(self):
        if self.contract_start_date and self.contract_end_date:
            if getdate(self.contract_end_date) < getdate(self.contract_start_date):
                frappe.throw(_("Contract End cannot be before Contract Start."))

        if not self.company:
            self.company = resolve_company("Habitat")

        apply_vat(self, flt(self.monthly_retainer) or flt(self.rate_per_visit))
