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


class TripFulfilmentLedger(Document):
    def validate(self):
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
