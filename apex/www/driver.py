# Copyright (c) 2026, AFMCO and contributors
"""Salis Driver portal — mobile SPA shell served at /driver.

Drivers are NOT Frappe users (full barcode cutover): a driver opens their PERSONAL
link (``/driver?d=<token>``) or scans the matching QR on a phone. Identity is the
unguessable token, resolved server-side by the driver endpoints
(``apex.salis.api.driver_portal``), which scope every query to one Salis Driver.

This page is therefore Guest-accessible (no login redirect): it validates the token
charset, stores it in an httpOnly cookie, and redirects to the clean ``/driver`` so
the raw token never lingers in the URL/history — exactly the ``www/masar.py`` pattern.
The CSRF token is exposed so the guest SPA's whitelisted POSTs pass Frappe's CSRF guard.
"""

import re

import frappe
from frappe.sessions import get_csrf_token
from frappe.utils import cint

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    DRIVER_TOKEN_COOKIE,
)
from apex.apex_core.utils.portal_bootstrap import apply_portal_appearance
from apex.apex_core.utils.portal_token_security import DRIVER, throttle_entry_token

# Same charset guard as the worker entry (www/masar.py): url-safe token only.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# Match the driver token TTL (180d) so the entry cookie outlives a single session.
_COOKIE_MAX_AGE_SECONDS = 180 * 24 * 60 * 60


def get_context(context):
    context.no_cache = 1
    context.csrf_token = get_csrf_token()

    # Barcode entry: validate ?d=<raw>, store it httpOnly, then redirect to the
    # clean /driver so the raw token is stripped from the URL/history.
    raw_token = frappe.form_dict.get("d") or ""
    valid_token = raw_token if _TOKEN_RE.match(raw_token) else ""
    if valid_token:
        # Defense-in-depth: charge the shared per-IP bad-token throttle for a
        # failed/unknown link before it is parked in the cookie; a valid link is
        # never charged and the redirect still fires so the secret leaves the URL.
        throttle_entry_token(DRIVER, valid_token)
        _set_token_cookie(valid_token)
        frappe.local.flags.redirect_location = "/driver"
        raise frappe.Redirect

    # Realtime config for the driver SPA (unchanged from the previous shell).
    conf = frappe.get_site_config()
    context.site_name = frappe.local.site
    context.socketio_port = cint(conf.get("socketio_port")) or 9000
    context.async_enabled = not cint(conf.get("disable_async"))
    context.dev_server = 1 if frappe.conf.developer_mode else 0

    context.driver_has_token = bool(_request_token_cookie())

    apply_portal_appearance(context)
    return context


def _set_token_cookie(token: str) -> None:
    """Persist the validated token in the httpOnly /driver cookie (best-effort).

	Guarded so a missing cookie_manager (a non-request render path) degrades to
	leaving the query-string token in place rather than 500-ing the page."""
    cm = getattr(frappe.local, "cookie_manager", None)
    if cm is None:
        return
    cm.set_cookie(
        DRIVER_TOKEN_COOKIE,
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
        return (request.cookies.get(DRIVER_TOKEN_COOKIE) or "").strip()
    except Exception:
        return ""
