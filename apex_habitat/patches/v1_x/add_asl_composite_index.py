# Copyright (c) 2026, AFMCO and contributors
"""Add a composite index on Accommodation Stock Ledger (is_cancelled, item_type, employee).

The custody/stock balance queries filter the ledger by these three columns together
(active rows of a given item type for an employee). A single composite index serves
that access path far better than the per-column search indexes alone. This index
cannot live in the DocType JSON (Frappe only emits single-column search_index rows),
so it is added here.

Idempotent: skips if the index already exists. Runs in post_model_sync so the table
and its synced columns exist.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Accommodation Stock Ledger"):
        return

    # Skip if the index already exists (ADD INDEX IF NOT EXISTS is not portable
    # across all MariaDB builds for composite indexes).
    existing = frappe.db.sql(
        "SHOW INDEX FROM `tabAccommodation Stock Ledger` "
        "WHERE Key_name = 'idx_asl_cancel_type_emp'"
    )
    if existing:
        return

    # [#asl9cx]
    try:
        frappe.db.sql(
            "ALTER TABLE `tabAccommodation Stock Ledger` "
            "ADD INDEX `idx_asl_cancel_type_emp` (`is_cancelled`, `item_type`, `employee`)"
        )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Patch: add idx_asl_cancel_type_emp failed",
        )
        raise

    frappe.db.commit()
