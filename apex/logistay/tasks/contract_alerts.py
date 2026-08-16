# Copyright (c) 2026, afmcoltd
"""Scheduled Telecom Contract status maintenance.

``TelecomContract._sync_status`` derives Active vs Expired from the contract
period, but only inside ``validate``, and Frappe never runs ``validate`` again
on a submitted document. A contract that is Active the day it is submitted
therefore stays Active forever once its own ``contract_end_date`` passes,
unless something re-derives the status later — this is that later
re-derivation, the same shape as Habitat's ``lease_expiry_watchlist``
(apex/habitat/tasks/residency.py).
"""

from __future__ import annotations

import frappe
from frappe.utils import today

_ROW_SAVEPOINT = "telecom_contract_expiry_row"


def contract_expiry_watch() -> None:
    """Flip every submitted, still-Active contract whose end date has passed to Expired.

    A direct field write, not a re-``save()``: ``status`` is read-only and
    derived, so this mirrors the same out-of-workflow write ``on_cancel``
    already uses for Terminated. Terminated contracts are never matched by the
    ``status == "Active"`` filter, so retirement is never overwritten here.
    """
    today_str = today()
    cursor = ""
    batch_size = 500
    while True:
        contracts = frappe.get_all(
            "Telecom Contract",
            filters={
                "docstatus": 1,
                "status": "Active",
                "contract_end_date": ["<", today_str],
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
                    title=f"Telecom contract expiry watch failed for {contract.name}"[:140],
                )

        cursor = contracts[-1].name
