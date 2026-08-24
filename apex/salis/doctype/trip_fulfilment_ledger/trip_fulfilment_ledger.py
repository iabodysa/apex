# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded


def on_doctype_update():
    add_unique_guarded(
        "Trip Fulfilment Ledger",
        ["dispatch_trip"],
        constraint_name="unique_tfl_trip",
    )


class TripFulfilmentLedger(Document):
    def validate(self):
        self._enforce_single_write_immutability()

    def _enforce_single_write_immutability(self):
        if not self.is_new():
            frappe.throw(
                _("Trip Fulfilment Ledger is a posted audit record and cannot be edited."),
                frappe.PermissionError,
            )
