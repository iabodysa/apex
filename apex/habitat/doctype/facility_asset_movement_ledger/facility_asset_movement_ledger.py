# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


UNIQUE_KEY = ["source_doctype", "source_name", "is_reversal"]
UNIQUE_KEY_NAME = "unique_faml_source"


def on_doctype_update():
    frappe.db.add_unique(
        "Facility Asset Movement Ledger",
        UNIQUE_KEY,
        constraint_name=UNIQUE_KEY_NAME,
    )


class FacilityAssetMovementLedger(Document):
    def before_insert(self):
        self.is_reversal = 1 if self.reversal_of else 0

    def validate(self):
        self._enforce_single_write_immutability()

    def _enforce_single_write_immutability(self):
        if not self.is_new():
            frappe.throw(
                _("Facility Asset Movement Ledger is a posted audit record and cannot be edited."),
                frappe.PermissionError,
            )
