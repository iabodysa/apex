"""Trip Fulfilment Ledger controller.

Read-only, machine-written audit memo. One row is inserted per completed
Dispatch Trip by the Dispatch Trip controller using ignore_permissions. No
DocPerm grants create/write/delete to any role; rows are never hand-entered.
Powers the daily transport-request fulfilment-rate KPI.
"""

from __future__ import annotations

from frappe.model.document import Document


class TripFulfilmentLedger(Document):
    pass
