# Copyright (c) 2026, afmcoltd
"""Guest-facing endpoints for portal device enrolment and self-service management.

Every endpoint here resolves identity from the request itself — an enrolment key
in the payload, or the audience's own bearer cookie via
``portal_identity.resolve_portal_subject`` — never from a client-supplied Employee
or Salis Driver id, matching every other Masar/driver portal endpoint in this app.
"""

from __future__ import annotations

import frappe

from apex.apex_core.doctype.portal_device.portal_device import (
    consume_enrolment_key,
    list_devices_for,
    revoke_own_device,
)
from apex.apex_core.utils.portal_identity import (
    DRIVER,
    WORKER,
    resolve_portal_subject,
    set_token_cookie,
)
from apex.apex_core.utils.rate_limit_identity import rate_limit

_ENROLMENT_COOKIE_MAX_AGE_SECONDS = 180 * 24 * 60 * 60


def _enrol(audience: str, key: str, device_label=None) -> dict:
    """Shared mechanics for the two audience-specific enrolment endpoints below:
    consume the key, cookie the freshly minted device secret exactly as
    ``apex/www/masar.py``/``apex/www/driver.py`` already cookie a Masar Worker
    Token, and tell the caller only whether it worked — never the secret's hash
    or the spent key."""
    raw_device = consume_enrolment_key(audience, key, device_label=device_label)
    set_token_cookie(audience, raw_device, _ENROLMENT_COOKIE_MAX_AGE_SECONDS)
    return {"enrolled": True}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def enrol_worker_device(key: str, device_label: str | None = None) -> dict:
    """Consume a worker's one-time enrolment key and cookie the new device."""
    return _enrol(WORKER, key, device_label)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def enrol_driver_device(key: str, device_label: str | None = None) -> dict:
    """Consume a driver's one-time enrolment key and cookie the new device."""
    return _enrol(DRIVER, key, device_label)


@frappe.whitelist(allow_guest=True)
def my_worker_devices() -> list:
    """The calling worker's own device list, resolved from their own cookie."""
    subject = resolve_portal_subject(WORKER, required=True)
    return list_devices_for(WORKER, subject)


@frappe.whitelist(allow_guest=True)
def my_driver_devices() -> list:
    """The calling driver's own device list, resolved from their own cookie."""
    subject = resolve_portal_subject(DRIVER, required=True)
    return list_devices_for(DRIVER, subject)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=60)
def revoke_my_worker_device(name: str) -> dict:
    """Revoke one of the calling worker's own devices."""
    subject = resolve_portal_subject(WORKER, required=True)
    revoked = revoke_own_device(WORKER, subject, name)
    return {"revoked": revoked}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=60)
def revoke_my_driver_device(name: str) -> dict:
    """Revoke one of the calling driver's own devices."""
    subject = resolve_portal_subject(DRIVER, required=True)
    revoked = revoke_own_device(DRIVER, subject, name)
    return {"revoked": revoked}
