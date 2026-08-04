# Copyright (c) 2026, AFMCO and contributors
"""The rate-limit window named after the HANDLER, not after the caller's spelling.

frappe resolves a request in two independent steps that never compare notes. The
handler comes from an attribute lookup on the module the ``cmd`` string names
(handler.py:294-303 -> __init__.py:1748-1750), and the whitelist check keys on the
function OBJECT that lookup returned (__init__.py:872). The window, meanwhile, is
named from the raw request field: ``rl:{form_dict.cmd}:{identity}``
(rate_limiter.py:155). So the ceiling is per SPELLING. A caller who knows two dotted
paths to one function is admitted twice over -- measured, not inferred:
``submit_resident_request`` has a 5/minute ceiling and admitted 10, and
``driver_portal.submit_fuel_request`` has 10/minute and admitted 20.

Two spellings are not an accident to be tidied away. 32 of the 35 live pairs come
from the driver portal package re-exporting its own submodules
(salis/api/driver_portal/__init__.py), and the SPA calls the SHORT name
(frontend/driver/src/pages/Fuel.vue:113) while the function is defined in the long
one -- so BOTH names are production and neither can be deleted. Deduplicating the
names would also only hold until the next re-export; naming the window after the
resolved function holds by construction.

The canonical name is ``{fn.__module__}.{fn.__name__}`` -- the DEFINING path, which
is the same identity frappe itself prints when it refuses a call (__init__.py:872).
It is intrinsic to the object, so a re-export added tomorrow folds into the existing
window with no list to maintain and nothing to remember.

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
    window's name. Import this instead of the framework's in every Apex endpoint;
    apex_core/utils/test_submit_rate_limit_identity.py fails the build if one goes
    back to the framework's directly.

    Leave ``key`` unset on a public endpoint. ``key`` is a form_dict lookup
    (rate_limiter.py:143) any caller can set from the query string, buying a private
    window per value; ``ip_based`` (default True) is what actually keys the window to
    the address (rate_limiter.py:110,141,147-150).
    """

    def decorator(fn):
        command = canonical_command(fn)
        charge = _frappe_rate_limit(
            key=key, limit=limit, seconds=seconds, methods=methods, ip_based=ip_based
        )(lambda: None)

        @wraps(fn)
        def wrapper(*args, **kwargs):
            """Charge the window under the canonical command, then run the endpoint.

            The charge goes through the framework's own decorator so the identity, the
            window length, the method gate and the 429 are never re-derived here. It
            wraps a no-op rather than ``fn``: the framework's wrapper CALLS what it
            wraps (rate_limiter.py:168), and letting it call the endpoint would hold
            the substituted cmd in place for the whole request body instead of the
            charge alone.

            No request means no traffic to meter and no cmd to substitute -- the
            framework's own first gate (rate_limiter.py:134) would pass this through
            anyway, so console and job callers touch no global.
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
