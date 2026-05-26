"""Rental Accrual Ledger controller.

Read-only, machine-written daily rental memo. No DocPerm grants create/write/
delete to any human role; rows are inserted only by the rental accrual engine
(``rental_engine.daily_rental_accrual``) using ignore_permissions. This DocType
posts NO General Ledger / accounting entry — each row is an operational memo.
"""

from __future__ import annotations

from frappe.model.document import Document


class RentalAccrualLedger(Document):
    pass
