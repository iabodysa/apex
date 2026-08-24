# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from frappe.model.document import Document
from apex.apex_core.utils.ledger_index import add_unique_guarded
from apex.apex_core.utils.party_link import sync_party_employee


class AccommodationLedger(Document):
    pass


def before_save(doc, method=None):
    sync_party_employee(doc)


def on_doctype_update():
    add_unique_guarded(
        "Accommodation Ledger",
        ["employee", "posting_date", "assignment", "building", "ledger_type"],
        constraint_name="unique_accl_daily_share",
    )
