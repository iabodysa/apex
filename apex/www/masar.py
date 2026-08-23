# Copyright (c) 2026, Apex contributors
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
        if valid_token and _token_resolves(valid_token):
            set_token_cookie(WORKER, valid_token, _COOKIE_MAX_AGE_SECONDS)
        else:
            delete_token_cookie(WORKER)
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
