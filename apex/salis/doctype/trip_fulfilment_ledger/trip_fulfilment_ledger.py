# Copyright (c) 2026, afmcoltd
"""Trip Fulfilment Ledger controller.

Read-only, machine-written audit memo. One row is inserted per completed
Dispatch Trip by the Dispatch Trip controller using ignore_permissions. No
DocPerm grants create/write/delete to any role; rows are never hand-entered.
Powers the daily transport-request fulfilment-rate KPI.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded


def on_doctype_update():
    """UNIQUE(dispatch_trip) — one completion memo per trip, enforced by the database.

    ``DispatchTrip._post_fulfilment_ledger`` guards the insert with a read that nothing
    enforces, so two concurrent completions of one trip both pass it and both post. The
    row is immutable once written, so neither of the two could then be corrected, and the
    fulfilment-rate KPI counts the trip twice. ``dispatch_trip`` alone is the key because
    cancel DELETES the row rather than posting a mirror, so no second row for one trip is
    ever legitimate.

    Created and kept in sync on migrate through Frappe's on_doctype_update hook. Guarded
    rather than declared as a field ``unique`` flag: pre-existing duplicate rows would
    abort a migrate, and this logs the blocking groups instead."""
    add_unique_guarded(
        "Trip Fulfilment Ledger",
        ["dispatch_trip"],
        constraint_name="unique_tfl_trip",
    )


class TripFulfilmentLedger(Document):
    def validate(self):
        """Blocks any edit to an already-persisted Trip Fulfilment Ledger row."""
        self._enforce_single_write_immutability()

    def _enforce_single_write_immutability(self):
        """Single-write audit memo: a posted row is immutable.

        Each ledger row is inserted once by the Dispatch Trip controller and is
        never re-saved (reversal deletes the row outright, it does not edit it).
        Block any update to an already-persisted row so a posted fulfilment record
        cannot be silently altered after the fact — the insert itself (``is_new``)
        is allowed through so the controller can post the row. validate() runs on
        every save, so this guards the form view, the REST resource, and any code
        path that re-saves an existing row."""
        if not self.is_new():
            frappe.throw(
                _("Trip Fulfilment Ledger is a posted audit record and cannot be edited."),
                frappe.PermissionError,
            )
