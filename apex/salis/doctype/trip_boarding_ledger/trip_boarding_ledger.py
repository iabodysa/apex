# Copyright (c) 2026, afmcoltd
"""Trip Boarding Ledger controller.

Read-only, machine-written audit memo. One row is inserted per worker's final
boarding outcome (Boarded / Absent) when a Dispatch Trip is finalized, by the
boarding engine using ignore_permissions. No DocPerm grants create/write/delete
to any role; rows are never hand-entered. Stabilises per-worker boarding reports
against later edits of the operational Trip Boarding State child.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class TripBoardingLedger(Document):
    def validate(self):
        """Blocks any edit to an already-persisted Trip Boarding Ledger row."""
        self._enforce_single_write_immutability()

    def _enforce_single_write_immutability(self):
        """Single-write audit memo: a posted row is immutable.

        Each ledger row is inserted once by the boarding engine and is never
        re-saved through the ORM. Reversal posts a NEW negative mirror row and
        flags the original via frappe.db.set_value (a direct DB write that does
        not run this controller), so neutralising a row never edits it here.
        Block any ORM update to an already-persisted row so a posted outcome
        cannot be silently altered; the insert itself (is_new) is allowed through
        so the engine can post the row. validate() runs on every save, so this
        guards the form view, the REST resource, and any code path re-saving an
        existing row."""
        if not self.is_new():
            frappe.throw(
                _("Trip Boarding Ledger is a posted audit record and cannot be edited."),
                frappe.PermissionError,
            )


def on_doctype_update():
    """Hard idempotency backstop, the one its three sibling ledgers already carry.

    ``boarding_engine`` guards both writes with a check-then-insert and no row lock,
    so a double-tapped depart post can interleave two reads before either insert and
    board the same worker twice. ``reversal_of`` is part of the key rather than a
    separate constraint because it separates the two guards without blocking either:
    an original row carries '' (a Link column is NOT NULL DEFAULT ''), so two
    originals for one trip+worker collide — which is what ``_ledger_exists``
    checks — while a reversal carries the original's name, so one trip+worker may
    still hold its mirror and only a SECOND reversal of the same original collides —
    which is what ``reverse_trip_boarding`` checks. A plain (dispatch_trip, employee)
    key would have made every reversal a duplicate entry.

    Created/kept in sync on migrate via Frappe's on_doctype_update hook. Guarded so
    pre-existing duplicate data logs rather than aborting migrate."""
    from apex.apex_core.utils.ledger_index import add_unique_guarded

    add_unique_guarded(
        "Trip Boarding Ledger",
        ["dispatch_trip", "employee", "reversal_of"],
        constraint_name="unique_tbl_trip_employee",
    )
