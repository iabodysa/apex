# Copyright (c) 2026, AFMCO and contributors
"""Disable legacy driver Website Users after passwordless barcode cutover.

Only a driver with a live token is cut over. System users, elevated-role staff,
Administrator, and Guest remain enabled. Issuance applies the same guard after
this idempotent migration has run, so fresh installs cut over at first issue.
"""

import frappe

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    _disable_legacy_driver_user,
)

def execute():
    tokened_drivers = set(
        frappe.get_all(
            "Masar Worker Token",
            filters={"holder_type": "Driver", "enabled": 1},
            pluck="driver",
        )
    )
    if not tokened_drivers:
        return

    disabled = 0
    for driver in tokened_drivers:
        disabled += int(_disable_legacy_driver_user(driver))

    if disabled:
        frappe.db.commit()
