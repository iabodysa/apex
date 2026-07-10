# Copyright (c) 2026, AFMCO and contributors
"""Timesheet Exception Log controller — append-only immutable audit.

Machine-written by ``logistay.ingestion_engine`` when a data-quality or
attendance exception is detected. Read-only; disposition lives in the exception
workbench, never as an edit to this row.
"""

from __future__ import annotations

from frappe.model.document import Document


class TimesheetExceptionLog(Document):
    pass
