# Copyright (c) 2026, AFMCO and contributors
"""The one atomic fixed-window counter behind every hand-rolled Apex throttle.

Two controls had to leave ``frappe.rate_limiter`` behind, each for a reason its key
cannot express: the boarding scan counts a server-resolved ACTOR rather than a
request key, and the portal bad-token window is one budget per ADDRESS spent across
every entry rather than one per ``form_dict.cmd`` (rate_limiter.py:155). Neither is a
place to also re-derive HOW a window is counted.

The framework counts with GET, then SETEX, then INCRBY (rate_limiter.py:134-166), and
that read-then-write is a TOCTOU race: a request whose GET saw an empty key can SETEX
it back to zero long after another request has filled the window, erasing every count
in it. A sufficiently parallel flood therefore holds the counter near zero and the
ceiling never fires — the one control that exists to make a flood visible goes quiet
exactly when the flood is worst.

INCR settles it in a single round trip and returns the post-increment value, so the
caller that sees 1 is the only one that opens the window and sets its TTL. Nothing is
read before it is written, so there is no interval for a second connection to occupy.
"""

from __future__ import annotations

import frappe
from frappe import _

# Public because apex_core/utils/test_front_desk_rate_limit.py drives the script itself to prove
# 32 concurrent callers really do get 32 distinct values.
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
