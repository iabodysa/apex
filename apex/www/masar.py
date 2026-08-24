# Copyright (c) 2026, Apex contributors
"""Masar — worker self-service app shell (Vue SPA served at /masar).

Masar is the worker's mobile self-service app: a transported and housed Employee opens
their PERSONAL link (``/masar?w=<token>``) on a phone and manages their profile,
accommodation, transport, and requests. Workers are NOT Frappe users — identity is an
enrolled DEVICE, resolved server-side by the worker endpoints
(``apex.salis.api.masar``), which scope every query to one Employee.

The link/QR carries a ONE-TIME enrolment key, not a standing bearer: the first request
that presents ``?w=<token>`` with no already-recognised device cookie spends that key
(``portal_device.consume_enrolment_key``) and cookies the freshly minted device secret
in its place — the token itself is never cookied. A request whose existing device
cookie already resolves is recognised on the cookie alone and never touches the key,
so a worker who is still signed in on this device can reopen the same link, or a fresh
one, without spending anything. A presented key that is missing, malformed, or already
spent, with no device cookie to fall back on, clears any stale cookie and lands on the
guest shell exactly as an unknown token does; recovering from there is a supervisor
issuing a fresh link, not a re-scan of the old one.

This page is therefore Guest-accessible (no login redirect). The order below is
load-bearing and must not be rearranged: charset-guard the query parameter, check the
existing device cookie before touching the key at all, then redirect to the clean path
so the secret leaves the address bar and the history. After that the SPA sends no
credential at all.

The socket globals published into the shell carry no identity: the room a worker may
join is handed to the client by ``get_worker_context``, which authenticated the token
first, and never derived in the browser.
"""

import re

import frappe
from apex.apex_core.doctype.portal_device.portal_device import consume_enrolment_key
from apex.apex_core.utils.portal_bootstrap import publish_portal_context
from apex.apex_core.utils.portal_identity import (
    WORKER,
    delete_token_cookie,
    presented_token,
    resolve_portal_subject,
    set_token_cookie,
)

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

_COOKIE_MAX_AGE_SECONDS = 180 * 24 * 60 * 60
WORKER_CAPABILITIES = (
    "worker.home",
    "worker.profile.read",
    "worker.accommodation.read",
    "worker.custody.read",
    "worker.trip.read",
    "worker.request.create",
    "worker.request.read",
)

def get_context(context):
    """Validates a worker token in the URL, cookies it and redirects, or bootstraps the guest SPA."""
    context.no_cache = 1

    query_token_supplied = "w" in frappe.form_dict
    raw_token = frappe.form_dict.get("w") or ""
    valid_token = raw_token if isinstance(raw_token, str) and _TOKEN_RE.fullmatch(raw_token) else ""
    if query_token_supplied:
        if not _recognised_by_cookie():
            _enrol_or_clear(valid_token)
        frappe.local.flags.redirect_location = "/masar/"
        raise frappe.Redirect

    frappe.local.lang = "ar"

    cookie_token = presented_token(WORKER)[0]
    subject = _resolve_token_subject(cookie_token) if cookie_token else None
    if cookie_token and not subject:
        delete_token_cookie(WORKER)
    return publish_portal_context(
        context,
        entry="worker",
        public_path="/masar/",
        initial_route="/home",
        capabilities=WORKER_CAPABILITIES if subject else (),
        subject=subject,
    )

def _recognised_by_cookie() -> bool:
    """Whether the request's own device cookie -- never the query string -- already resolves."""
    cookie_token = presented_token(WORKER)[0]
    return bool(cookie_token) and _token_resolves(cookie_token)

def _enrol_or_clear(valid_token: str) -> None:
    """Spend a presented enrolment key exactly once and cookie the minted device
    secret, or clear any stale cookie when the key is absent, malformed, or already
    spent."""
    if valid_token:
        try:
            raw_device = consume_enrolment_key(WORKER, valid_token)
        except frappe.PermissionError:
            delete_token_cookie(WORKER)
        else:
            set_token_cookie(WORKER, raw_device, _COOKIE_MAX_AGE_SECONDS)
    else:
        delete_token_cookie(WORKER)

def _token_resolves(token: str) -> bool:
    """Whether the credential still names an active worker."""
    try:
        return bool(resolve_portal_subject(WORKER, token, required=True))
    except frappe.PermissionError:
        return False

def _resolve_token_subject(token: str) -> str | None:
    try:
        return resolve_portal_subject(WORKER, token, required=True)
    except frappe.PermissionError:
        return None
