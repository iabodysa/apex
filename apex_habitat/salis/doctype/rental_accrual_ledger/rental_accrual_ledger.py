"""Rental Accrual Ledger controller.

Read-only, machine-written daily rental memo. No DocPerm grants create/write/
delete to any human role; rows are inserted only by the rental accrual engine
(``rental_engine.daily_rental_accrual``) using ignore_permissions. This DocType
posts NO General Ledger / accounting entry — each row is an operational memo.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class RentalAccrualLedger(Document):
    pass


def on_doctype_update():
    """Hard idempotency backstop: a composite UNIQUE index on (vehicle,
    accrual_date) so the daily one-row-per-vehicle-per-day accrual cannot be
    double-posted at the DB level even if the engine's check-then-insert is
    bypassed by a race. Created/kept in sync on migrate via Frappe's
    on_doctype_update hook."""
    frappe.db.add_unique(
        "Rental Accrual Ledger",
        ["vehicle", "accrual_date"],
        constraint_name="unique_ral_vehicle_date",
    )
