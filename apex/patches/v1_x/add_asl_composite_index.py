# Copyright (c) 2026, AFMCO and contributors
"""Add a composite index on Accommodation Stock Ledger (is_cancelled, item_type, employee).

The custody/stock balance queries filter the ledger by these three columns together
(active rows of a given item type for an employee). A single composite index serves
that access path far better than the per-column search indexes alone.

The index now lives in the controller ``on_doctype_update`` (via the shared
``add_index_guarded`` helper) so fresh installs — which mark patches complete without
running them — also get it. This patch delegates to the same helper so already-migrated
sites still create it in the same idempotent way. Safe to prune once every deployed site
has run the on_doctype_update path.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Accommodation Stock Ledger"):
        return

    # [#asl9cx]
    from apex.apex_core.utils.ledger_index import add_index_guarded

    add_index_guarded(
        "Accommodation Stock Ledger",
        ["is_cancelled", "item_type", "employee"],
        "idx_asl_cancel_type_emp",
    )
    frappe.db.commit()
