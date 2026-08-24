# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe

from apex.apex_core.doctype.portal_device.portal_device import (
    consume_enrolment_key,
    list_devices_for,
    mark_onboarded,
    revoke_own_device,
    set_device_language,
)
from apex.apex_core.utils.portal_identity import (
    DRIVER,
    WORKER,
    presented_token,
    resolve_portal_subject,
    set_token_cookie,
)
from apex.apex_core.utils.rate_limit_identity import rate_limit

_ENROLMENT_COOKIE_MAX_AGE_SECONDS = 180 * 24 * 60 * 60


def _enrol(audience: str, key: str, device_label=None) -> dict:
    raw_device = consume_enrolment_key(audience, key, device_label=device_label)
    set_token_cookie(audience, raw_device, _ENROLMENT_COOKIE_MAX_AGE_SECONDS)
    return {"enrolled": True}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def enrol_worker_device(key: str, device_label: str | None = None) -> dict:
    return _enrol(WORKER, key, device_label)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def enrol_driver_device(key: str, device_label: str | None = None) -> dict:
    return _enrol(DRIVER, key, device_label)


@frappe.whitelist(allow_guest=True)
def my_worker_devices() -> list:
    subject = resolve_portal_subject(WORKER, required=True)
    return list_devices_for(WORKER, subject)


@frappe.whitelist(allow_guest=True)
def my_driver_devices() -> list:
    subject = resolve_portal_subject(DRIVER, required=True)
    return list_devices_for(DRIVER, subject)


def _finish_onboarding(audience: str) -> dict:
    resolve_portal_subject(audience, required=True)
    return {"onboarded": mark_onboarded(audience, presented_token(audience)[0])}


def _choose_language(audience: str, language: str) -> dict:
    resolve_portal_subject(audience, required=True)
    return {"chosen": set_device_language(audience, presented_token(audience)[0], language)}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def choose_worker_language(language: str) -> dict:
    return _choose_language(WORKER, language)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def choose_driver_language(language: str) -> dict:
    return _choose_language(DRIVER, language)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def finish_worker_onboarding() -> dict:
    return _finish_onboarding(WORKER)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def finish_driver_onboarding() -> dict:
    return _finish_onboarding(DRIVER)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=60)
def revoke_my_worker_device(name: str) -> dict:
    subject = resolve_portal_subject(WORKER, required=True)
    revoked = revoke_own_device(WORKER, subject, name)
    return {"revoked": revoked}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=60)
def revoke_my_driver_device(name: str) -> dict:
    subject = resolve_portal_subject(DRIVER, required=True)
    revoked = revoke_own_device(DRIVER, subject, name)
    return {"revoked": revoked}
