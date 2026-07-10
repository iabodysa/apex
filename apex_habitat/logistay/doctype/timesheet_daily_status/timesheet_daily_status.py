# Copyright (c) 2026, AFMCO and contributors
"""Timesheet Daily Status — child row of Timesheet Line.

One row per day of the period: day number, the canonical status code
(present/absent/leave/...), and any overtime hours. The normalized day grid
every client format (adapters A..H + PAPER) flattens into. The controller is
intentionally thin; rows are written by the ingestion engine (E-INGEST).
"""

from __future__ import annotations

from frappe.model.document import Document


class TimesheetDailyStatus(Document):
    pass
