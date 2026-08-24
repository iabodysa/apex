# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded

UNIQUE_KEY = ["vehicle", "accrual_date", "reversal_of"]
UNIQUE_KEY_NAME = "unique_ral_vehicle_date"


class RentalAccrualLedger(Document):
    pass


def _drop_stale_unique_key():
    try:
        rows = frappe.db.sql(
            """
            SELECT COLUMN_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = %s
            ORDER BY SEQ_IN_INDEX
            """,
            ("tabRental Accrual Ledger", UNIQUE_KEY_NAME),
            as_dict=True,
        )
    except Exception:
        return
    live_columns = [r["COLUMN_NAME"] for r in rows]
    if not live_columns or live_columns == UNIQUE_KEY:
        return
    try:
        frappe.db.sql(
            "ALTER TABLE `tabRental Accrual Ledger` DROP INDEX `{0}`".format(UNIQUE_KEY_NAME)
        )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Could not drop stale {UNIQUE_KEY_NAME}"[:140],
        )


def on_doctype_update():
    _drop_stale_unique_key()
    add_unique_guarded(
        "Rental Accrual Ledger",
        UNIQUE_KEY,
        constraint_name=UNIQUE_KEY_NAME,
    )
