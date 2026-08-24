# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class SafetyFindingLedger(Document):
    def on_update(self):
        if self.is_new():
            return
        if not self.flags.ignore_validate_update_after_submit and self.get_doc_before_save():
            frappe.throw(
                _("Safety Finding Ledger rows are immutable and cannot be edited."),
                title=_("Immutable Record"),
            )

    def on_trash(self):
        if frappe.flags.in_install or frappe.flags.in_migrate:
            return
        frappe.throw(
            _("Safety Finding Ledger rows cannot be deleted. Cancel the Safety "
              "Round to post a reversal instead."),
            title=_("Immutable Record"),
        )
