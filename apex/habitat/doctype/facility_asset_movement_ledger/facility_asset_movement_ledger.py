# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded


def on_doctype_update():
    add_unique_guarded(
        "Facility Asset Movement Ledger",
        ["source_doctype", "source_name", "reversal_of"],
        constraint_name="unique_faml_source",
    )


class FacilityAssetMovementLedger(Document):
    def validate(self):
        self._enforce_single_write_immutability()

    def _enforce_single_write_immutability(self):
        if not self.is_new():
            frappe.throw(
                _("Facility Asset Movement Ledger is a posted audit record and cannot be edited."),
                frappe.PermissionError,
            )
