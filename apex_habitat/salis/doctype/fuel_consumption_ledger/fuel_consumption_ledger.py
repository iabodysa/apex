# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

"""Fuel Consumption Ledger controller.

Hidden, machine-written fuel consumption ledger. No DocPerm grants write/create
to any human role; rows are inserted by the fuel engine scheduled jobs using
ignore_permissions. Rows are operational memos with no financial (GL) impact.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class FuelConsumptionLedger(Document):
    pass


def on_doctype_update():
    """Hard idempotency backstop: a composite UNIQUE index on the source key so a
    double-post (same originating record) fails at the DB level even if the
    engine's check-then-insert is bypassed by a race. Mirrors the engine's
    ``(source_type, source_name)`` idempotency key. Created/kept in sync on
    migrate via Frappe's on_doctype_update hook."""
    frappe.db.add_unique(
        "Fuel Consumption Ledger",
        ["source_type", "source_name"],
        constraint_name="unique_fcl_source",
    )
