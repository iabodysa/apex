# Copyright (c) 2026, Apex contributors
"""Salis Driver portal — mobile SPA shell served at /driver.

Drivers are NOT Frappe users (full barcode cutover): a driver opens their PERSONAL
link (``/driver?d=<token>``) or scans the matching QR on a phone. Identity is an
enrolled DEVICE, resolved server-side by the driver endpoints
(``apex.salis.api.driver_portal``), which scope every query to one Salis Driver.

The link/QR carries a ONE-TIME enrolment key, not a standing bearer: the first
request that presents ``?d=<token>`` with no already-recognised device cookie spends
that key (``portal_device.consume_enrolment_key``) and cookies the freshly minted
device secret in its place — the token itself is never cookied. A request whose
existing device cookie already resolves is recognised on the cookie alone and never
touches the key, so a driver who is still signed in on this device can reopen the
same link, or a fresh one, without spending anything. A presented key that is
missing, malformed, or already spent, with no device cookie to fall back on, clears
any stale cookie and lands on the guest shell exactly as an unknown token does;
recovering from there is a supervisor issuing a fresh link, not a re-scan of the old
one.

This page is therefore Guest-accessible (no login redirect): it charset-guards the
query parameter, checks the existing device cookie before touching the key at all,
and redirects to the clean ``/driver`` so the raw token never lingers in the
URL/history — exactly the ``www/masar.py`` pattern. The CSRF token is exposed so the
guest SPA's whitelisted POSTs pass Frappe's CSRF guard.
"""

import re

import frappe

from apex.apex_core.doctype.portal_device.portal_device import consume_enrolment_key
from apex.apex_core.utils.portal_bootstrap import publish_portal_context
from apex.apex_core.utils.portal_identity import (
    DRIVER,
    delete_token_cookie,
    presented_token,
    resolve_portal_subject,
    set_token_cookie,
)

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
        if not _recognised_by_cookie():
            _enrol_or_clear(valid_token)
        frappe.local.flags.redirect_location = "/driver/"
        raise frappe.Redirect

    frappe.local.lang = "ar"

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


def _recognised_by_cookie() -> bool:
    """Whether the request's own device cookie -- never the query string -- already resolves."""
    cookie_token = presented_token(DRIVER)[0]
    return bool(cookie_token) and _token_resolves(cookie_token)


def _enrol_or_clear(valid_token: str) -> None:
    """Spend a presented enrolment key exactly once and cookie the minted device
    secret, or clear any stale cookie when the key is absent, malformed, or already
    spent."""
    if valid_token:
        try:
            raw_device = consume_enrolment_key(DRIVER, valid_token)
        except frappe.PermissionError:
            delete_token_cookie(DRIVER)
        else:
            set_token_cookie(DRIVER, raw_device, _COOKIE_MAX_AGE_SECONDS)
    else:
        delete_token_cookie(DRIVER)


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
