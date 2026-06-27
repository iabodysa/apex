"""Facility Asset Movement Ledger controller.

Read-only, machine-written audit memo. One row is posted per submitted Facility
Asset Movement by ``asset_movement_engine.post_asset_movement`` using
ignore_permissions, and a negated reversal row is posted on cancel. No DocPerm
grants create/write/delete to any role; rows are never hand-entered. This is the
queryable relocation history the in-place Facility Asset location update lacks.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class FacilityAssetMovementLedger(Document):
    def validate(self):
        self._enforce_single_write_immutability()

    def _enforce_single_write_immutability(self):
        """Single-write audit memo: a posted row is immutable.

        Each ledger row is inserted once by the engine and never re-saved; cancel
        posts a separate negated reversal row rather than editing the original.
        Block any update to an already-persisted row so a posted movement record
        cannot be silently altered after the fact — the insert (``is_new``) is
        allowed through. validate() runs on every save, so this guards the form
        view, the REST resource, and any code path that re-saves an existing row.
        """
        if not self.is_new():
            frappe.throw(
                _("Facility Asset Movement Ledger is a posted audit record and cannot be edited."),
                frappe.PermissionError,
            )
