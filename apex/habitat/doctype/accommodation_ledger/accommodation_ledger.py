# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded
from apex.apex_core.utils.party_link import sync_party_employee

UNIQUE_KEY = ["source_doctype", "source_name", "ledger_type", "posting_date", "is_reversal"]
UNIQUE_KEY_NAME = "unique_accl_source"
RETIRED_UNIQUE_KEY_NAME = "unique_accl_daily_share"


class AccommodationLedger(Document):
    def before_insert(self):
        self.is_reversal = 1 if self.reversal_of else 0


def before_save(doc, method=None):
    sync_party_employee(doc)


def on_doctype_update():
    add_unique_guarded(
        "Accommodation Ledger",
        UNIQUE_KEY,
        constraint_name=UNIQUE_KEY_NAME,
    )
