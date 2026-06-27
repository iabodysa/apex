# Copyright (c) 2026, AFMCO and contributors

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
    # System-written ledger: block any ORM re-save of an existing row so the audit
    # trail is tamper-evident. The engine posts rows via insert() (flags.in_insert)
    # and flips is_cancelled via frappe.db.set_value (bypasses controller hooks),
    # so neither legitimate engine path trips this guard — only an edit of an
    # already-stored row through save() does.
    def on_update(self):
        if not self.flags.in_insert and not frappe.flags.in_install:
            frappe.throw(
                _("Cleaning Compliance Ledger rows are immutable and cannot be edited.")
            )

    def on_trash(self):
        # System Manager may purge (housekeeping); no other path deletes a row.
        if "System Manager" not in frappe.get_roles(frappe.session.user):
            frappe.throw(_("Cleaning Compliance Ledger rows cannot be deleted."))
