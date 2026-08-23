# Copyright (c) 2026, afmcoltd
"""The wrong-code counter for every one-time-code flow, kept where a throw cannot erase it.

A flow that counts misses in a DocType field does not count them at all. ``db_set``
defaults to ``commit=False`` (``frappe/model/document.py:1234``); a ``frappe.throw`` leaves
``rollback`` True at ``frappe/app.py:103``, because the ``else: sync_database`` branch at
``:147`` only runs when nothing was raised; and ``:154-155`` rolls back on any UNSAFE
method, which POST is (``frappe/auth.py:31``). So the attempt count is written and
discarded by the same request that reports the miss: the limit is never reached, the
lockout is never stamped, and a 6-digit code can be guessed without bound.

Redis is the fix rather than a mid-request commit: a counter that never joins the
transaction cannot be rolled back by one. This wraps the app's own atomic INCR window,
which already refuses with 429 on the hit that passes the limit.

The numbers stay with the flow. A module owns its own attempt limit and lockout length —
custody and telecom need not agree — so they are arguments, never constants here.

REMOVE THIS WHEN THE FRAMEWORK NO LONGER NEEDS IT, and the condition is exact so an
upgrade sweep can settle it without re-deriving the bug: this file exists only because a
write made before ``frappe.throw`` inside a POST endpoint does not survive the request.
The day ``frappe/app.py`` stops rolling back a request whose handler threw, or ``db_set``
gains a durable-on-throw path, the counter can go back into ``otp_attempts`` and this
module and its two call sites delete together. Check those two lines first, not this text.

Its siblings — the other places Apex routes around a framework defect rather than a
missing feature — are ``apex_core/utils/rate_window.py`` (frappe's own limiter resets its
window under concurrency) and ``apex_core/overrides/notification.py`` (core wraps in-app
and email delivery in one try, so an email failure kills the in-app fallback). An upgrade
that touches rate limiting, notifications or request teardown should read all three.
"""

from __future__ import annotations

import frappe

from apex.apex_core.utils.rate_window import charge_window, peek_window


def _miss_key(doctype: str, name: str) -> str:
    return f"otp-miss:{doctype}:{name}"


def charge_wrong_code(doctype: str, name: str, *, attempts: int, lockout_minutes: int) -> int:
    """Count one wrong code against this document and refuse once ``attempts`` is passed.

    Keyed per document, so guessing at one record never locks another out.
    """
    return charge_window(
        _miss_key(doctype, name),
        lockout_minutes * 60,
        attempts,
    )


def is_locked_out(doctype: str, name: str, *, attempts: int) -> bool:
    """True once this document has taken enough wrong codes to refuse the next one.

    The caller must ask this BEFORE comparing the code. Charging on the miss path
    alone counts guesses but never stops one: every request still evaluates its
    guess, and a correct guess arriving mid-lockout is accepted because the
    counter is only consulted after the comparison has already returned.

    The boundary matches ``charge_window``, which refuses the hit that carries the
    count PAST ``attempts`` — so ``attempts`` misses already on record means the
    next attempt is refused, right or wrong.
    """
    return peek_window(_miss_key(doctype, name)) >= attempts


def clear_lockout(doctype: str, name: str) -> None:
    """Forget this document's wrong codes, because the code they were guessing is gone.

    Issuing a fresh code has to lift the lockout or the reissue cannot be used: the
    legitimate holder of the new code is refused for the rest of the window by misses
    charged against a code that no longer opens anything. The DocType's own
    ``otp_attempts`` and ``otp_locked_until`` are not the counter — see this module's
    docstring — so clearing them lifts nothing.

    ``frappe.cache.delete_value`` (frappe/utils/redis_wrapper.py:133) applies
    ``make_key`` itself, so the raw key name is passed here exactly as
    :func:`charge_window` charges it. Passing an already-prefixed name would delete a
    key nothing wrote and leave the real lockout standing.
    """
    frappe.cache.delete_value(_miss_key(doctype, name))
