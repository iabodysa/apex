# Copyright (c) 2026, AFMCO and contributors
"""Timesheet engine for the Logistay module.

Background engine that mirrors the apex no-GL, system-written ledger pattern
(``apex.salis.fuel_engine`` / ``habitat.accommodation_ledger``): it
posts an immutable Timesheet Ledger row for each COMPLETE Timesheet Line that is
not yet ledgered. Idempotent on ``(source_doctype, source_name)`` — the engine
checks for an existing entry AND a DB unique index backs it up.

No money is computed here: the ledger captures attendance facts (payable days /
shifts / overtime) only. Rates, pay and VAT are joined by the rate-card,
reconciliation, invoice and payroll engines, which are registered as separate
build tasks (they need owner-confirmed contract/money data before their logic
can be written).

Scheduled job:
* ``post_timesheet_ledger`` (daily) — posts one Timesheet Ledger row per newly
  COMPLETE Timesheet Line. Safe to re-run; already-ledgered lines are skipped.
"""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime

LINE_DOCTYPE = "Timesheet Line"
LEDGER_DOCTYPE = "Timesheet Ledger"
BATCH_SIZE = 500


def post_timesheet_ledger() -> int:
    """Post an immutable Timesheet Ledger row for each COMPLETE, un-ledgered
    Timesheet Line. Returns the number of rows posted."""
    lines = frappe.get_all(
        LINE_DOCTYPE,
        filters={"ts_completeness": "COMPLETE"},
        fields=[
            "name",
            "ts_worker",
            "ts_period",
            "ts_payable_days",
            "ts_shifts",
            "ts_ot_hours",
        ],
        limit=BATCH_SIZE,
    )

    posted = 0
    for line in lines:
        if _already_ledgered(line.name):
            continue
        _post_one(line)
        posted += 1

    if posted:
        frappe.db.commit()
    return posted


def _already_ledgered(source_name: str) -> bool:
    return bool(
        frappe.db.exists(
            LEDGER_DOCTYPE,
            {
                "source_doctype": LINE_DOCTYPE,
                "source_name": source_name,
                "reversal_of": ["is", "not set"],
            },
        )
    )


def _post_one(line) -> None:
    frappe.get_doc(
        {
            "doctype": LEDGER_DOCTYPE,
            "worker": line.ts_worker,
            "period": line.ts_period,
            "payable_days": line.ts_payable_days,
            "shifts": line.ts_shifts,
            "ot_hours": line.ts_ot_hours,
            "logged_at": now_datetime(),
            "source_type": LINE_DOCTYPE,
            "source_doctype": LINE_DOCTYPE,
            "source_name": line.name,
        }
    ).insert(ignore_permissions=True)  # audit-ok — engine posts an immutable ledger row server-side
