# Copyright (c) 2026, AFMCO and contributors
"""Safety Finding Ledger controller.

Read-only, machine-written immutable audit memo. One row is posted per finding
observed on a Safety Round's executions when the round is submitted, via
``habitat.safety_engine`` using ignore_permissions. No DocPerm grants
create/write/delete to any role; rows are never hand-entered.

WHY: safety/audit findings otherwise live only on the mutable parent reports
(Safety Task Execution finding rows), so a closed finding can silently reopen or
be rewritten. This ledger captures an immutable snapshot of each finding at
submit time, so safety reports are stable and the closed/open history is fixed.

A cancelled Safety Round does not delete its rows — the engine posts a negating
reversal row (``is_cancelled=1``, ``reversal_of`` set), mirroring the Salis fuel
ledger reversal idiom. The guard below makes the immutability explicit: once a
row exists it cannot be edited (only the system-set reversal flag may be
stamped on insert), and it can never be hand-deleted.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class SafetyFindingLedger(Document):
    def on_update(self):
        # Immutable after creation: any field change to an existing row is
        # rejected. Inserts pass through (is_new); the engine never edits a row
        # after inserting it.
        if self.is_new():
            return
        if not self.flags.ignore_validate_update_after_submit and self.get_doc_before_save():
            frappe.throw(
                _("Safety Finding Ledger rows are immutable and cannot be edited."),
                title=_("Immutable Record"),
            )

    def on_trash(self):
        # Never hand-delete a ledger row; cancellation posts a reversal instead.
        # frappe.flags.in_install / in_migrate let teardown + framework paths
        # through (e.g. uninstall), but normal deletion is blocked.
        if frappe.flags.in_install or frappe.flags.in_migrate:
            return
        frappe.throw(
            _("Safety Finding Ledger rows cannot be deleted. Cancel the Safety "
              "Round to post a reversal instead."),
            title=_("Immutable Record"),
        )
