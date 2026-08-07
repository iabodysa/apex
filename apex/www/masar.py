# Copyright (c) 2026, afmcoltd
"""Masar — worker self-service app shell (Vue SPA served at /masar).

Masar is the worker's mobile self-service app: a transported and housed Employee
opens their PERSONAL link (``/masar?w=<token>``) on a phone and manages their
profile, accommodation, transport, and requests. Workers are NOT Frappe users —
identity is the unguessable token, resolved server-side by the worker endpoints
(``apex.salis.api.masar``), which scope every query to one Employee.

This page is therefore Guest-accessible (no login redirect): it only serves the
built SPA shell and passes the token through to the client. The CSRF token is
exposed using ``frappe.sessions.get_csrf_token()`` (same pattern as the driver
portal) so the SPA's whitelisted calls work behind Frappe's CSRF guard. The
appearance (theme + optional brand overrides) reuses the Salis Portal Theme.

The old read-only "my worker route today" view that previously lived here has
moved into the driver portal (/driver → "My Route"); see
``apex.salis.api.driver_portal.my_worker_route_today``.
"""

import re

import frappe
from frappe.sessions import get_csrf_token

from apex.apex_core.utils.portal_bootstrap import apply_portal_appearance
from apex.apex_core.utils.portal_token_security import WORKER, throttle_entry_token

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

MASAR_TOKEN_COOKIE = "masar_wt"
_COOKIE_MAX_AGE_SECONDS = 180 * 24 * 60 * 60


def get_context(context):
    """Validates a worker token in the URL, cookies it and redirects, or bootstraps the guest SPA."""
    context.no_cache = 1


    context.csrf_token = get_csrf_token()

    raw_token = frappe.form_dict.get("w") or ""
    valid_token = raw_token if _TOKEN_RE.match(raw_token) else ""
    if valid_token:
        throttle_entry_token(WORKER, valid_token)
        _set_token_cookie(valid_token)
        frappe.local.flags.redirect_location = "/masar"
        raise frappe.Redirect

    context.masar_has_token = bool(_request_token_cookie())

    apply_portal_appearance(context)
    return context


def _set_token_cookie(token: str) -> None:
    """Persist the validated token in the httpOnly /masar cookie (best-effort).

	Guarded so a missing cookie_manager (e.g. a non-request render path) degrades to
	leaving the query-string token in place rather than 500-ing the page."""
    cm = getattr(frappe.local, "cookie_manager", None)
    if cm is None:
        return
    cm.set_cookie(
        MASAR_TOKEN_COOKIE,
        token,
        httponly=True,
        samesite="Lax",
        max_age=_COOKIE_MAX_AGE_SECONDS,
    )


def _request_token_cookie() -> str:
    """The token already stored in the request's httpOnly cookie, or ''."""
    request = getattr(frappe.local, "request", None)
    if request is None:
        return ""
    try:
        return (request.cookies.get(MASAR_TOKEN_COOKIE) or "").strip()
    except Exception:
        return ""
