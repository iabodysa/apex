# Copyright (c) 2026, AFMCO and contributors
"""Adaptive ingestion engine for the Logistay module (scaffold).

The adaptive layer turns heterogeneous, incomplete, multi-source, per-branch,
mixed-media client inputs into ONE clean canonical Timesheet Line set with
per-field provenance, and records every data-quality exception it finds in the
immutable Timesheet Exception Log.

STATUS: scaffold. The format adapters (the parsers), the client-plus-supervisor
merge, and the gap-check rules are delivered by the "ingestion adapters" build
task — they depend on the per-format catalogue (evidenced, not on owner money
data), plus the TS Intake Source / TS Format Adapter / TS Status Code Map
config DocTypes. Until then ``normalize_pending_intakes`` is an inert no-op so
the module is safe to install and schedule.

The one piece live now is ``log_exception`` — the single writer for the
append-only Timesheet Exception Log, ready for the adapters to call.
"""

from __future__ import annotations

from typing import Optional

import frappe
from frappe.utils import now_datetime

EXCEPTION_LOG_DOCTYPE = "Timesheet Exception Log"


def log_exception(
    exception_type: str,
    entity: str,
    severity: str = "GATE",
    period_month: Optional[str] = None,
    field_ref: Optional[str] = None,
    detail: Optional[str] = None,
    source_doctype: Optional[str] = None,
    source_name: Optional[str] = None,
) -> str:
    """Append one immutable Timesheet Exception Log row. Returns its name.

    The single writer for the exception audit trail — the adapters and gap-check
    rules call this instead of inserting the log DocType directly, so there is
    one place the record shape is owned.
    """
    doc = frappe.get_doc(
        {
            "doctype": EXCEPTION_LOG_DOCTYPE,
            "exception_type": exception_type,
            "severity": severity,
            "entity": entity,
            "period_month": period_month,
            "field_ref": field_ref,
            "detail": detail,
            "detected_at": now_datetime(),
            "source_doctype": source_doctype,
            "source_name": source_name,
        }
    ).insert(ignore_permissions=True)  # audit-ok — engine logs an immutable exception row server-side
    return doc.name


def normalize_pending_intakes() -> int:
    """Parse + merge + gap-check every pending intake into canonical Timesheet
    Lines. Inert scaffold: returns 0 until the ingestion-adapters task delivers
    the parsers and the TS Intake Source config DocType. Kept as the stable
    entry point the scheduler will call once those land.
    """
    return 0
