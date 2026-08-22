# Copyright (c) 2026, afmcoltd
"""Charge Frappe rate limits under the resolved handler's canonical path."""

from __future__ import annotations

from functools import wraps

import frappe
from frappe.rate_limiter import rate_limit as _frappe_rate_limit

_ABSENT = object()

def canonical_command(fn) -> str:
    """The single ``cmd`` ``fn`` is metered under, whatever the caller spelled."""
    return f"{fn.__module__}.{fn.__name__}"

def rate_limit(
    key: str | None = None,
    limit=5,
    seconds: int = 24 * 60 * 60,
    methods="ALL",
    ip_based: bool = True,
):
    """Drop-in for ``frappe.rate_limiter.rate_limit`` that ignores the caller's spelling.

    Same arguments, same meaning, same enforcement -- the only difference is the
    window's name. Import this instead of the framework's in every Apex endpoint, so
    two spellings of the same action share one window instead of one each.
    """

    def decorator(fn):
        """Returns a wrapper that charges the rate-limit window under the function's own canonical name."""
        command = canonical_command(fn)
        charge = _frappe_rate_limit(
            key=key, limit=limit, seconds=seconds, methods=methods, ip_based=ip_based
        )(lambda: None)

        @wraps(fn)
        def wrapper(*args, **kwargs):
            """Charge the window under the canonical command, then run the endpoint.

            """
            form_dict = getattr(frappe.local, "form_dict", None)
            if form_dict is None or not getattr(frappe.local, "request", None):
                charge()
                return fn(*args, **kwargs)

            spelled = form_dict["cmd"] if "cmd" in form_dict else _ABSENT
            form_dict["cmd"] = command
            try:
                charge()
            finally:
                if spelled is _ABSENT:
                    form_dict.pop("cmd", None)
                else:
                    form_dict["cmd"] = spelled
            return fn(*args, **kwargs)

        wrapper._apex_rate_limit = (limit, seconds)
        return wrapper

    return decorator
