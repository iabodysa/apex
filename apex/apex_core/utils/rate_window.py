# Copyright (c) 2026, afmcoltd
"""The one atomic fixed-window counter behind every hand-rolled Apex throttle.

INCR settles it in a single round trip and returns the post-increment value, so the
caller that sees 1 is the only one that opens the window and sets its TTL. Nothing is
read before it is written, so there is no interval for a second connection to occupy.
"""

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
    """Charge one hit against the fixed window ``name`` and return its new count.

    Raises ``RateLimitExceededError`` (HTTP 429) on the hit that carries the count
    past ``limit``, so a caller only has to decide WHICH bucket to charge.

    ``name`` is the RAW key name: ``frappe.cache.make_key``
    (frappe/utils/redis_wrapper.py:41) is applied here so no call site has to remember
    it, and none can apply it twice — the one thing ``make_key`` cannot do is refuse a
    key it has already prefixed, and a double-prefixed name counts in a bucket nothing
    else reads while a cleanup aimed at the real one clears nothing.

    The TTL is set only when the window opens, never refreshed, so a steady stream
    cannot hold one window open forever.
    """
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
    """Read the window's current count without charging it.

    For a gate that must refuse BEFORE it evaluates the request — a lockout that
    runs after the comparison has already answered the attacker's question.

    ``frappe.cache.get_value`` cannot read this counter: it ``pickle.loads`` what
    it finds (``frappe/utils/redis_wrapper.py:97``) and INCR stores a plain
    integer. So the raw key is read directly, built with the same ``make_key`` the
    charger used.
    """
    value = frappe.cache.get(frappe.cache.make_key(name))
    return int(value) if value else 0

