# Copyright (c) 2026, afmcoltd


from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


UNIQUE_KEY = ["source_doctype", "source_name", "source_detail_no", "is_reversal"]
UNIQUE_KEY_NAME = "unique_mcl_source"


class MaintenanceCostLedger(Document):
    def before_insert(self):
        self.is_reversal = 1 if self.reversal_of else 0

    def on_update(self):
        if not self.is_new() and not self.flags.in_insert:
            frappe.throw(_("Maintenance Cost Ledger rows are immutable and cannot be edited."))


def on_doctype_update():
    frappe.db.add_unique(
        "Maintenance Cost Ledger",
        UNIQUE_KEY,
        constraint_name=UNIQUE_KEY_NAME,
    )
