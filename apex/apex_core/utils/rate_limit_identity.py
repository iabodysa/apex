# Copyright (c) 2026, afmcoltd
"""The rate-limit window named after the HANDLER, not after the caller's spelling.

Two spellings are not an accident to be tidied away. 32 of the 35 live pairs come
from the driver portal package re-exporting its own submodules
(``salis/api/driver_portal/__init__.py``), while clients may call the short name and
the function is defined in the long one. Both names are production. Deduplicating the
names would also only hold until the next re-export; naming the window after the
resolved function holds by construction.

Everything else stays frappe's. The identity (``<ip>`` or ``<ip>:<form field>``), the
window length, the TTL-once behaviour, the 429 and its message all come from the
installed limiter -- this only decides which NAME it charges, by substituting the
canonical command for the caller's for the duration of the charge and putting the
caller's back before any endpoint code runs. ``frappe.local.form_dict`` is a process
global that no transaction rolls back, so the swap covers the charging call alone
and restores absence as absence.

Deploy note: for the 34 endpoints that had a second path, the LIVE window name
changes once (``rl:apex.salis.api.driver_portal.submit_fuel_request:<ip>`` becomes
``rl:apex.salis.api.driver_portal.fuel.submit_fuel_request:<ip>``). Windows in flight
at that moment are abandoned and reopened -- a one-off, bounded by the 60s window.
Endpoints with a single path keep the name they already had.
"""

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

        return wrapper

    return decorator
