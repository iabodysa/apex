# Copyright (c) 2026, afmcoltd
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

from apex.apex_core.utils.ledger_index import add_unique_guarded


def on_doctype_update():
    """UNIQUE(source_doctype, source_name, reversal_of) — the tuple that identifies
    one posting, so a raced or retried submit cannot write a second row.

    ``asset_movement_engine`` guards both writes with a read-then-insert that nothing
    enforces: the posting path skips a source that already has an original, and
    ``reverse_asset_movement`` skips an original that already has a reversal. Two
    concurrent submits both pass their read. ``reversal_of`` is in the key because an
    original and its mirror share a source and must both be allowed to exist.

    Created and kept in sync on migrate through Frappe's on_doctype_update hook.
    Guarded rather than declared as a field ``unique`` flag: pre-existing duplicate
    rows would abort a migrate, and this logs the blocking groups instead."""
    add_unique_guarded(
        "Facility Asset Movement Ledger",
        ["source_doctype", "source_name", "reversal_of"],
        constraint_name="unique_faml_source",
    )


class FacilityAssetMovementLedger(Document):
    def validate(self):
        """Blocks any update to an already-persisted ledger row, allowing only the initial insert."""
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
