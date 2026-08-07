# Copyright (c) 2026, afmcoltd
"""Operational Depreciation Policy controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class OperationalDepreciationPolicy(Document):
    def validate(self):
        """Blocks saving when useful life is not positive or residual value percent is outside 0 to 100."""
        if self.useful_life_years is not None and flt(self.useful_life_years) <= 0:
            frappe.throw(_("Useful Life (Years) must be greater than zero."))
        if not 0 <= flt(self.residual_value_pct) <= 100:
            frappe.throw(_("Residual Value (%) must be between 0 and 100."))
