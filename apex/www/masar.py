# Copyright (c) 2026, afmcoltd
"""Masar — worker self-service app shell (Vue SPA served at /masar).

Masar is the worker's mobile self-service app: a transported and housed Employee opens
their PERSONAL link (``/masar?w=<token>``) on a phone and manages their profile,
accommodation, transport, and requests. Workers are NOT Frappe users — identity is the
unguessable token, resolved server-side by the worker endpoints
(``apex.salis.api.masar``), which scope every query to one Employee.

This page is therefore Guest-accessible (no login redirect). The order below is
load-bearing and must not be rearranged: charset-guard the query parameter, run it
through the shared bad-token throttle BEFORE it is trusted enough to cookie, set the
httpOnly SameSite=Lax cookie, then redirect to the clean path so the secret leaves the
address bar and the history. After that the SPA sends no credential at all.

The socket globals published into the shell carry no identity: the room a worker may
join is handed to the client by ``get_worker_context``, which authenticated the token
first, and never derived in the browser.
"""

import re

import frappe
from frappe.sessions import get_csrf_token
from frappe.utils import cint

from apex.apex_core.utils.portal_bootstrap import apply_portal_appearance
from apex.apex_core.utils.portal_language import render_in_arabic
from apex.apex_core.utils.portal_token_security import WORKER, resolve_portal_subject

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

MASAR_TOKEN_COOKIE = "masar_wt"
_COOKIE_MAX_AGE_SECONDS = 180 * 24 * 60 * 60


def get_context(context):
    """Validates a worker token in the URL, cookies it and redirects, or bootstraps the guest SPA."""
    context.no_cache = 1
    context.csrf_token = get_csrf_token()

    query_token_supplied = "w" in frappe.form_dict
    raw_token = frappe.form_dict.get("w") or ""
    valid_token = raw_token if isinstance(raw_token, str) and _TOKEN_RE.fullmatch(raw_token) else ""
    if query_token_supplied:
        if valid_token and _token_resolves(valid_token):
            _set_token_cookie(valid_token)
        else:
            _delete_cookie(MASAR_TOKEN_COOKIE)
        frappe.local.flags.redirect_location = "/masar/"
        raise frappe.Redirect

    render_in_arabic()

    conf = frappe.get_site_config()
    context.site_name = frappe.local.site
    context.socketio_port = cint(conf.get("socketio_port")) or 9000
    context.async_enabled = not cint(conf.get("disable_async"))
    context.dev_server = 1 if frappe.conf.developer_mode else 0

    cookie_token = _request_token_cookie()
    context.masar_has_token = bool(cookie_token and _token_resolves(cookie_token))
    if cookie_token and not context.masar_has_token:
        _delete_cookie(MASAR_TOKEN_COOKIE)

    apply_portal_appearance(context)
    return context


def _token_resolves(token: str) -> bool:
    """Whether the credential still names an active worker."""
    try:
        return bool(resolve_portal_subject(WORKER, token, required=True))
    except frappe.PermissionError:
        return False


def _set_token_cookie(token: str) -> None:
    """Persist the validated token in the httpOnly site cookie (best-effort).

	Guarded so a missing cookie_manager (e.g. a non-request render path) degrades to
	leaving the query-string token in place rather than 500-ing the page. No ``path`` is
	passed, so the cookie defaults to ``/`` and rides every request to this site."""
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


def _delete_cookie(name: str) -> None:
    cm = getattr(frappe.local, "cookie_manager", None)
    if cm is not None:
        cm.delete_cookie(name)


def _request_token_cookie() -> str:
    """The token already stored in the request's httpOnly cookie, or ''."""
    request = getattr(frappe.local, "request", None)
    if request is None:
        return ""
    try:
        return (request.cookies.get(MASAR_TOKEN_COOKIE) or "").strip()
    except Exception:
        return ""
