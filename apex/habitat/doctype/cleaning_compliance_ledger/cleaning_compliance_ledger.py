# Copyright (c) 2026, afmcoltd

"""Cleaning Compliance Ledger controller.

Read-only, system-written audit memo. One immutable row is posted per room of a
submitted Cleaning Log by ``habitat.cleaning_engine`` using ignore_permissions.
No DocPerm grants create/write to any role; rows are never hand-entered and are
reversed (negative mirror + is_cancelled), never edited. Powers the cleaning
compliance KPI so historical compliance is stable when a Cleaning Log is amended.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class CleaningComplianceLedger(Document):
    def on_update(self):
        """Blocks any edit to an existing Cleaning Compliance Ledger row outside of insert or install."""
        if not self.flags.in_insert and not frappe.flags.in_install:
            frappe.throw(
                _("Cleaning Compliance Ledger rows are immutable and cannot be edited.")
            )

    def on_trash(self):
        """Blocks deleting a Cleaning Compliance Ledger row unless the user holds System Manager."""
        if "System Manager" not in frappe.get_roles(frappe.session.user):
            frappe.throw(_("Cleaning Compliance Ledger rows cannot be deleted."))
