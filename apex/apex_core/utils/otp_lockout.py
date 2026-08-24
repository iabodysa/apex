# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe

from apex.apex_core.utils.rate_window import charge_window, peek_window


def _miss_key(doctype: str, name: str) -> str:
    return f"otp-miss:{doctype}:{name}"


def charge_wrong_code(doctype: str, name: str, *, attempts: int, lockout_minutes: int) -> int:
    return charge_window(
        _miss_key(doctype, name),
        lockout_minutes * 60,
        attempts,
    )


def is_locked_out(doctype: str, name: str, *, attempts: int) -> bool:
    return peek_window(_miss_key(doctype, name)) >= attempts


def clear_lockout(doctype: str, name: str) -> None:
    frappe.cache.delete_value(_miss_key(doctype, name))
