# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from frappe.utils.user import get_users_with_role


def sim_operations_users() -> list[str]:
    return get_users_with_role("SIM Operations User")
