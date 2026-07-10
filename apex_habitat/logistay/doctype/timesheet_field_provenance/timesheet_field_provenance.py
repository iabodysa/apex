# Copyright (c) 2026, AFMCO and contributors
"""Timesheet Field Provenance — child row of Timesheet Line.

One row per canonical field whose value needed a human or adapter decision:
which source supplied it, who entered it, and when. This is the dispute
defence — a client challenge on any attendance figure resolves to the row
that shows where the number came from. The controller is intentionally thin;
rows are written by the ingestion engine (E-INGEST), never hand-edited.
"""

from __future__ import annotations

from frappe.model.document import Document


class TimesheetFieldProvenance(Document):
    pass
