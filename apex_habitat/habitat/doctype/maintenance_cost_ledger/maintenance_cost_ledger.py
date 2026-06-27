# Copyright (c) 2026, AFMCO and contributors

"""Maintenance Cost Ledger controller.

Read-only, machine-written audit memo. One row is inserted per Maintenance
Work Order procurement item by the maintenance engine using ignore_permissions
when the Work Order is completed. No DocPerm grants create/write/delete to any
role; rows are never hand-entered. Reversal is a negative mirror row plus an
is_cancelled flag, never a delete, so a historical cost query stays stable when
a Work Order is later cancelled.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class MaintenanceCostLedger(Document):
    def on_update(self):
        """A posted ledger row is immutable. Block any later edit so the cost
        trail cannot be rewritten; the engine sets is_cancelled via db_set (which
        fires no on_update doc_event), so flagging a reversal never trips this."""
        if not self.is_new() and not self.flags.in_insert:
            frappe.throw(_("Maintenance Cost Ledger rows are immutable and cannot be edited."))


def on_doctype_update():
    """Hard idempotency backstop: a composite UNIQUE index on the source key so a
    double-post (same Work Order + same procurement row) fails at the DB level
    even if the engine's check-then-insert is bypassed by a race. Mirrors the
    engine's (source_doctype, source_name, source_detail_no) idempotency key;
    reversal rows carry reversal_of (set) and a distinct detail no so they do not
    collide with their original."""
    from apex_habitat.apex_core.utils.ledger_index import add_unique_guarded

    add_unique_guarded(
        "Maintenance Cost Ledger",
        ["source_doctype", "source_name", "source_detail_no", "reversal_of"],
        constraint_name="unique_mcl_source",
    )
