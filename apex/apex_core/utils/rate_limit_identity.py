# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from functools import wraps

import frappe
from frappe.rate_limiter import rate_limit as _frappe_rate_limit

_ABSENT = object()

def canonical_command(fn) -> str:
    return f"{fn.__module__}.{fn.__name__}"

def rate_limit(
    key: str | None = None,
    limit=5,
    seconds: int = 24 * 60 * 60,
    methods="ALL",
    ip_based: bool = True,
):

    def decorator(fn):
        command = canonical_command(fn)
        charge = _frappe_rate_limit(
            key=key, limit=limit, seconds=seconds, methods=methods, ip_based=ip_based
        )(lambda: None)

        @wraps(fn)
        def wrapper(*args, **kwargs):
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
