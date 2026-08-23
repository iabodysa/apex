# Copyright (c) 2026, afmcoltd
"""Who holds a Logistay notification role, in one place.

Three callers need the live SIM Operations User roster to notify — the daily
suspended/lost SIM digest, the contract-expiry watch, and the custody engine's
own Lost/Suspend event notice — and each must see the same enabled, real-user
set or two of them drift on who gets told. A second copy of the exclusion rule
(Administrator, Guest, disabled users) anywhere else is that drift.
"""

from __future__ import annotations

import frappe


def sim_operations_users() -> list[str]:
    """Enabled, real Users holding the SIM Operations User role."""
    users = frappe.get_all(
        "Has Role",
        filters={"role": "SIM Operations User", "parenttype": "User"},
        pluck="parent",
    )
    return [
        u
        for u in set(users)
        if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")
    ]
