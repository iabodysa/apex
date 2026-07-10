# Copyright (c) 2026, AFMCO and contributors
"""Timesheet Line controller — the canonical normalized attendance record.

One record per worker per client/branch cycle. It is the MERGE output of the
ingestion layer (a client artifact + a supervisor artifact) with per-field
provenance, and the sole input contract consumed downstream by the rate-card,
reconciliation, invoice and payroll engines.

Attendance ONLY: rates, pay and VAT are never stored here (the rate card is
joined downstream). The controller keeps only structural guards; the adaptive
parsing, merge and gap-check logic lives in ``logistay.ingestion_engine`` and
the completeness gate is stamped there, not in user edits.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class TimesheetLine(Document):
    def validate(self) -> None:
        self._validate_non_negative()

    def _validate_non_negative(self) -> None:
        for fieldname in ("ts_payable_days", "ts_shifts", "ts_ot_hours"):
            value = self.get(fieldname)
            if value is not None and value < 0:
                frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(fieldname))))
