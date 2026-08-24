# Copyright (c) 2026, afmcoltd


from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded


class MaintenanceCostLedger(Document):
    def on_update(self):
        if not self.is_new() and not self.flags.in_insert:
            frappe.throw(_("Maintenance Cost Ledger rows are immutable and cannot be edited."))


def on_doctype_update():
    add_unique_guarded(
        "Maintenance Cost Ledger",
        ["source_doctype", "source_name", "source_detail_no", "reversal_of"],
        constraint_name="unique_mcl_source",
    )
