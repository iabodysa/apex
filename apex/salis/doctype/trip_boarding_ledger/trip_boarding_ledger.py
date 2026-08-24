# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded


class TripBoardingLedger(Document):
    def validate(self):
        self._enforce_single_write_immutability()

    def _enforce_single_write_immutability(self):
        if not self.is_new():
            frappe.throw(
                _("Trip Boarding Ledger is a posted audit record and cannot be edited."),
                frappe.PermissionError,
            )


def on_doctype_update():
    add_unique_guarded(
        "Trip Boarding Ledger",
        ["dispatch_trip", "employee", "reversal_of"],
        constraint_name="unique_tbl_trip_employee",
    )
