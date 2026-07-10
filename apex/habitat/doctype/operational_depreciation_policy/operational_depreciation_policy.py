# Copyright (c) 2026, AFMCO and contributors
"""Operational Depreciation Policy controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class OperationalDepreciationPolicy(Document):
    def validate(self):
        # [#aubbvz]
        if self.useful_life_years is not None and flt(self.useful_life_years) <= 0:
            frappe.throw(_("Useful Life (Years) must be greater than zero."))
        # A residual value is a fraction of cost — only 0..100 percent is meaningful.
        if not 0 <= flt(self.residual_value_pct) <= 100:
            frappe.throw(_("Residual Value (%) must be between 0 and 100."))
