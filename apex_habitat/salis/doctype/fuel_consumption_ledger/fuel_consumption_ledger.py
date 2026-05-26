# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

"""Fuel Consumption Ledger controller.

Hidden, machine-written fuel consumption ledger. No DocPerm grants write/create
to any human role; rows are inserted by the fuel engine scheduled jobs using
ignore_permissions. Rows are operational memos with no financial (GL) impact.
"""

from __future__ import annotations

from frappe.model.document import Document


class FuelConsumptionLedger(Document):
    pass
