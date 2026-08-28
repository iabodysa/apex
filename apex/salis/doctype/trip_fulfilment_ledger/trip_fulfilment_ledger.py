# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded

UNIQUE_KEY = ["dispatch_trip", "is_reversal"]
UNIQUE_KEY_NAME = "unique_tfl_trip"


def on_doctype_update():
    add_unique_guarded(
        "Trip Fulfilment Ledger",
        UNIQUE_KEY,
        constraint_name=UNIQUE_KEY_NAME,
    )


class TripFulfilmentLedger(Document):
    def before_insert(self):
        self.is_reversal = 1 if self.reversal_of else 0

    def validate(self):
        self._enforce_single_write_immutability()

    def _enforce_single_write_immutability(self):
        if not self.is_new():
            frappe.throw(
                _("Trip Fulfilment Ledger is a posted audit record and cannot be edited."),
                frappe.PermissionError,
            )
