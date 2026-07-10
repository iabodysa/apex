# Copyright (c) 2026, AFMCO and contributors
"""Mapping Profile controller — the no-code ingestion configuration.

Tells a parser how one client/branch source format maps onto the canonical
Timesheet Line fields. Effective-dated: a format revision is a NEW version, so
the controller guards only the effective window here; the parser selection and
merge logic live in ``logistay.ingestion_engine``.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate
from frappe.model.document import Document


class MappingProfile(Document):
    def validate(self) -> None:
        self._validate_effective_window()

    def _validate_effective_window(self) -> None:
        if not (self.ts_effective_from and self.ts_effective_to):
            return
        if getdate(self.ts_effective_to) < getdate(self.ts_effective_from):
            frappe.throw(_("Effective To cannot be before Effective From."))
