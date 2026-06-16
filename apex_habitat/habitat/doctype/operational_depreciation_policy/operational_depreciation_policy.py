"""Operational Depreciation Policy controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class OperationalDepreciationPolicy(Document):
    def validate(self):
        # [#hfsb8e]
        # [#putscs]
        # [#8eon6a]
        # [#6zgvyk]
        if self.useful_life_years is not None and flt(self.useful_life_years) <= 0:
            frappe.throw(_("Useful Life (Years) must be greater than zero."))
