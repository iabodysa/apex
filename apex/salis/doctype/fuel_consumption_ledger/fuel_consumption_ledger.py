# Copyright (c) 2026, afmcoltd


from __future__ import annotations

import frappe
from frappe.model.document import Document


UNIQUE_KEY = ["source_type", "source_name", "is_reversal"]
UNIQUE_KEY_NAME = "unique_fcl_source"


class FuelConsumptionLedger(Document):
    def before_insert(self):
        self.is_reversal = 1 if self.reversal_of else 0


def on_doctype_update():
    frappe.db.add_unique(
        "Fuel Consumption Ledger",
        UNIQUE_KEY,
        constraint_name=UNIQUE_KEY_NAME,
    )
