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

from apex.apex_core.utils.portal_bootstrap import publish_portal_context
from apex.apex_core.utils.portal_identity import (
    DRIVER,
    delete_token_cookie,
    presented_token,
    resolve_portal_subject,
    set_token_cookie,
)
from apex.apex_core.utils.portal_language import render_in_arabic

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

_COOKIE_MAX_AGE_SECONDS = 180 * 24 * 60 * 60
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
            set_token_cookie(DRIVER, valid_token, _COOKIE_MAX_AGE_SECONDS)
        else:
            delete_token_cookie(DRIVER)
        frappe.local.flags.redirect_location = "/driver/"
        raise frappe.Redirect

    render_in_arabic()

    cookie_token = presented_token(DRIVER)[0]
    subject = _resolve_token_subject(cookie_token) if cookie_token else None
    if cookie_token and not subject:
        delete_token_cookie(DRIVER)
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
        return bool(resolve_portal_subject(DRIVER, token))
    except frappe.PermissionError:
        return False


def _resolve_token_subject(token: str) -> str | None:
    try:
        return resolve_portal_subject(DRIVER, token)
    except frappe.PermissionError:
        return None
