# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _

INCR_AND_EXPIRE_SCRIPT = """
local value = redis.call("INCR", KEYS[1])
if value == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
return value
"""


def charge_window(name: str, window_seconds: int, limit: int) -> int:
    value = frappe.cache.eval(
        INCR_AND_EXPIRE_SCRIPT,
        1,
        frappe.cache.make_key(name),
        window_seconds,
    )
    if int(value) > limit:
        frappe.throw(
            _("You hit the rate limit because of too many requests. Please try after sometime."),
            frappe.RateLimitExceededError,
        )
    return int(value)


def peek_window(name: str) -> int:
    value = frappe.cache.get(frappe.cache.make_key(name))
    return int(value) if value else 0

