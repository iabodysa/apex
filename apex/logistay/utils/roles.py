# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe


def sim_operations_users() -> list[str]:
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
