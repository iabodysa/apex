# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.document import Document


UNIQUE_KEY = ["vehicle", "accrual_date", "is_reversal"]
UNIQUE_KEY_NAME = "unique_ral_vehicle_date"


class RentalAccrualLedger(Document):
    def before_insert(self):
        self.is_reversal = 1 if self.reversal_of else 0


def on_doctype_update():
    frappe.db.add_unique(
        "Rental Accrual Ledger",
        UNIQUE_KEY,
        constraint_name=UNIQUE_KEY_NAME,
    )
