# Copyright (c) 2026, Apex contributors

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
    cookie_token = presented_token(WORKER)[0]
    return bool(cookie_token) and _token_resolves(cookie_token)

def _enrol_or_clear(valid_token: str) -> None:
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
    try:
        return bool(resolve_portal_subject(WORKER, token, required=True))
    except frappe.PermissionError:
        return False

def _resolve_token_subject(token: str) -> str | None:
    try:
        return resolve_portal_subject(WORKER, token, required=True)
    except frappe.PermissionError:
        return None
