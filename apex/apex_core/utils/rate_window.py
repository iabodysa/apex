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

    ``name`` is the RAW key name: ``make_key`` is applied here so no call site has to
    remember it, and none can apply it twice (a double-prefixed name counts in a key
    nothing else reads, and a cleanup aimed at the real one clears nothing).

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
