# Copyright (c) 2026, afmcoltd


from __future__ import annotations

from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded

UNIQUE_KEY = ["source_type", "source_name", "is_reversal"]
UNIQUE_KEY_NAME = "unique_fcl_source"


class FuelConsumptionLedger(Document):
    def before_insert(self):
        self.is_reversal = 1 if self.reversal_of else 0


def on_doctype_update():
    add_unique_guarded(
        "Fuel Consumption Ledger",
        UNIQUE_KEY,
        constraint_name=UNIQUE_KEY_NAME,
    )
