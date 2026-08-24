# Copyright (c) 2026, afmcoltd


from __future__ import annotations

from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded


class FuelConsumptionLedger(Document):
    pass


def on_doctype_update():
    add_unique_guarded(
        "Fuel Consumption Ledger",
        ["source_type", "source_name"],
        constraint_name="unique_fcl_source",
    )
