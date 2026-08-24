# Copyright (c) 2026, afmcoltd


from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class CleaningComplianceLedger(Document):
    def on_update(self):
        if not self.flags.in_insert and not frappe.flags.in_install:
            frappe.throw(
                _("Cleaning Compliance Ledger rows are immutable and cannot be edited.")
            )

    def on_trash(self):
        if "System Manager" not in frappe.get_roles(frappe.session.user):
            frappe.throw(_("Cleaning Compliance Ledger rows cannot be deleted."))
