# Copyright (c) 2026, Apex contributors
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

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    DRIVER_TOKEN_COOKIE,
    resolve_driver_token,
)
from apex.apex_core.utils.portal_bootstrap import publish_portal_context
from apex.apex_core.utils.portal_language import render_in_arabic

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

_COOKIE_MAX_AGE_SECONDS = 180 * 24 * 60 * 60
DRIVER_LINK_DEAD_COOKIE = "driver_link_dead"
_LINK_DEAD_MAX_AGE_SECONDS = 5 * 60
DRIVER_CAPABILITIES = (
    "driver.today",
    "driver.profile.read",
    "driver.employee.accommodation.read",
    "driver.employee.custody.read",
    "driver.employee.request.read",
    "driver.trip.execute",
    "driver.trip.read",
)


def get_context(context):
    """Validates a driver token in the URL, cookies it and redirects, or bootstraps the guest SPA."""
    context.no_cache = 1

    query_token_supplied = "d" in frappe.form_dict
    raw_token = frappe.form_dict.get("d") or ""
    valid_token = raw_token if isinstance(raw_token, str) and _TOKEN_RE.fullmatch(raw_token) else ""
    if query_token_supplied:
        if valid_token and _token_resolves(valid_token):
            _set_token_cookie(valid_token)
            _clear_dead_link_marker()
        else:
            _delete_cookie(DRIVER_TOKEN_COOKIE)
            _set_dead_link_marker()
        frappe.local.flags.redirect_location = "/driver/"
        raise frappe.Redirect

    render_in_arabic()

    cookie_token = _request_token_cookie()
    subject = _resolve_token_subject(cookie_token) if cookie_token else None
    _consume_dead_link_marker()
    if cookie_token and not subject:
        _delete_cookie(DRIVER_TOKEN_COOKIE)
    return publish_portal_context(
        context,
        entry="driver",
        public_path="/driver/",
        initial_route="/today",
        capabilities=DRIVER_CAPABILITIES if subject else (),
        subject=subject,
    )


def _token_resolves(token: str) -> bool:
    """Whether the credential still names an active driver, not merely a legal string."""
    try:
        return bool(resolve_driver_token(token))
    except frappe.PermissionError:
        return False


def _resolve_token_subject(token: str) -> str | None:
    try:
        return resolve_driver_token(token)
    except frappe.PermissionError:
        return None


def _set_token_cookie(token: str) -> None:
    """Persist the validated token in the httpOnly site cookie (best-effort).

	Guarded so a missing cookie_manager (a non-request render path) degrades to
	leaving the query-string token in place rather than 500-ing the page. No ``path``
	is passed, so the cookie defaults to ``/`` and rides every request to this site."""
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


def _set_dead_link_marker() -> None:
    """Carry only a short-lived failure flag across the query-stripping redirect."""
    cm = getattr(frappe.local, "cookie_manager", None)
    if cm is None:
        return
    cm.set_cookie(
        DRIVER_LINK_DEAD_COOKIE,
        "1",
        httponly=True,
        samesite="Lax",
        max_age=_LINK_DEAD_MAX_AGE_SECONDS,
    )


def _clear_dead_link_marker() -> None:
    _delete_cookie(DRIVER_LINK_DEAD_COOKIE)


def _consume_dead_link_marker() -> bool:
    request = getattr(frappe.local, "request", None)
    if request is None:
        return False
    try:
        is_dead = request.cookies.get(DRIVER_LINK_DEAD_COOKIE) == "1"
    except Exception:
        return False
    if is_dead:
        _clear_dead_link_marker()
    return is_dead


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
        return (request.cookies.get(DRIVER_TOKEN_COOKIE) or "").strip()
    except Exception:
        return ""
