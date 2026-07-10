# Copyright (c) 2026, AFMCO and contributors
"""Timesheet Ledger controller — immutable posted worker-hours fact.

Mirrors the apex no-GL ledger idiom (``fuel_consumption_ledger``,
``accommodation_stock_ledger``): system-written, read-only, reverse-not-delete.
One row per COMPLETE Timesheet Line, posted by ``logistay.timesheet_engine``.

Idempotency is enforced two ways: the engine checks for an existing entry
before inserting, and a DB-level unique index on ``(source_doctype,
source_name)`` blocks any duplicate posting that slips past the engine. A
reversal row carries its own distinct source pointer (the reversed ledger's
name) so it never collides with the original posting.
"""

from __future__ import annotations

from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded


class TimesheetLedger(Document):
    pass


def on_doctype_update():
    # Belt-and-suspenders: block a duplicate posting for the same source document.
    # Guarded so any pre-existing duplicate data logs instead of aborting migrate.
    add_unique_guarded(
        "Timesheet Ledger",
        ["source_doctype", "source_name"],
        constraint_name="uq_timesheet_ledger_source",
    )
