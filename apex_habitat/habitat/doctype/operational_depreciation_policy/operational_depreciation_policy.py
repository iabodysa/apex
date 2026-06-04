"""Operational Depreciation Policy controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class OperationalDepreciationPolicy(Document):
    def validate(self):
        # useful_life_years is reqd (the mandatory check handles a missing value with its
        # own MandatoryError), but the Int field still ACCEPTS 0 and negatives — a logically
        # invalid policy that would silently make assets "never depreciate". Reject a present
        # but non-positive value here; leave None to the mandatory check (guards stack).
        if self.useful_life_years is not None and flt(self.useful_life_years) <= 0:
            frappe.throw(_("Useful Life (Years) must be greater than zero."))
