# Copyright (c) 2026, Apex contributors

import re
from urllib.parse import quote

import frappe

from apex.apex_core.doctype.portal_device.portal_device import (
    consume_enrolment_key,
    device_language,
    onboarding_complete,
)
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
    context.no_cache = 1

    query_token_supplied = "d" in frappe.form_dict
    raw_token = frappe.form_dict.get("d") or ""
    valid_token = raw_token if isinstance(raw_token, str) and _TOKEN_RE.fullmatch(raw_token) else ""
    if query_token_supplied:
        known = presented_token(DRIVER)[0]
        device_token = known if _token_resolves(known) else _enrol_or_clear(valid_token)
        frappe.local.flags.redirect_location = _landing_path(device_token)
        raise frappe.Redirect

    cookie_token = presented_token(DRIVER)[0]
    frappe.local.lang = device_language(DRIVER, cookie_token) or "ar"

    subject = _resolve_token_subject(cookie_token) if cookie_token else None
    if cookie_token and not subject:
        delete_token_cookie(DRIVER)
    return publish_portal_context(
        context,
        entry="driver",
        public_path="/driver/",
        initial_route=_initial_route(cookie_token, subject),
        capabilities=DRIVER_CAPABILITIES if subject else (),
        subject=subject,
    )


def _initial_route(cookie_token: str, subject: str | None) -> str:
    if not subject or onboarding_complete(DRIVER, cookie_token):
        return "/today"
    return "/welcome"


def _landing_path(device_token: str) -> str:
    subject = _resolve_token_subject(device_token) if device_token else None
    if not subject:
        return "/driver/"
    employee = frappe.db.get_value("Salis Driver", subject, "employee")
    return f"/driver/?id={quote(employee or subject, safe='')}"


def _enrol_or_clear(valid_token: str) -> str:
    if not valid_token:
        delete_token_cookie(DRIVER)
        return ""
    try:
        raw_device = consume_enrolment_key(DRIVER, valid_token)
    except frappe.PermissionError:
        delete_token_cookie(DRIVER)
        return ""
    set_token_cookie(DRIVER, raw_device, _COOKIE_MAX_AGE_SECONDS)
    return raw_device or ""


def _token_resolves(token: str) -> bool:
    if not token:
        return False
    try:
        return bool(resolve_portal_subject(DRIVER, token))
    except frappe.PermissionError:
        return False


def _resolve_token_subject(token: str) -> str | None:
    try:
        return resolve_portal_subject(DRIVER, token)
    except frappe.PermissionError:
        return None
