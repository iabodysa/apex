# Copyright (c) 2026, afmcoltd
"""Scheduled Telecom Contract expiry watch.

``TelecomContract._sync_status`` derives Active vs Expired from the contract period,
but it runs only inside ``validate`` — Frappe never calls ``validate`` again on a
docstatus-1 document. A contract read as Active at submit time therefore stays Active
forever once its ``contract_end_date`` passes, because nothing revisits it. This job
carries the single-field flip (``db_set``, the same out-of-workflow write ``on_cancel``
already uses for Terminated) that submission cannot repeat on its own.
"""

from __future__ import annotations

import frappe
from frappe.utils import today

_ROW_SAVEPOINT = "telecom_contract_row"


def contract_expiry_watchlist() -> None:
    """Flip every submitted, past-end-date Active Telecom Contract to Expired."""
    cursor = ""
    batch_size = 500
    while True:
        contracts = frappe.get_all(
            "Telecom Contract",
            filters={
                "docstatus": 1,
                "status": "Active",
                "contract_end_date": ["<", today()],
                "name": [">", cursor],
            },
            fields=["name"],
            order_by="name asc",
            limit_page_length=batch_size,
        )
        if not contracts:
            break

        for contract in contracts:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                frappe.db.set_value("Telecom Contract", contract.name, "status", "Expired")
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Telecom contract expiry watchlist failed for {contract.name}"[:140],
                )

        cursor = contracts[-1].name
