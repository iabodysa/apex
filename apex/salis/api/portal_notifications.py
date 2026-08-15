# Copyright (c) 2026, afmcoltd
"""Worker and driver device opt-in endpoints for background notifications.

The save passes ``ignore_permissions`` because the caller is a token subject with no user record —
``resolve_portal_subject`` maps the bearer token to a worker or driver, and there are no roles to
consult. The subscription is that subject's own device registration, and the token resolution
above is what authorises writing it.
"""

import frappe
from frappe import _

from apex.apex_core.utils.portal_identity import DRIVER, WORKER, resolve_portal_subject
from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.salis.api import web_push

_SUBSCRIPTION_DOCTYPE = "Portal Push Subscription"
_ENTRY_AUDIENCE = {"worker": WORKER, "driver": DRIVER}


def _resolve_identity(entry: str) -> tuple[str, str]:
    try:
        audience = _ENTRY_AUDIENCE[entry]
    except KeyError:
        frappe.throw(_("Unknown portal notification entry."), frappe.PermissionError)
    return audience, resolve_portal_subject(audience, required=True)


def _clean(value, maximum: int, label: str) -> str:
    value = (value or "").strip()
    if not value or len(value) > maximum:
        frappe.throw(_("{0} is invalid.").format(label), frappe.ValidationError)
    return value


def _belongs_to(row, audience: str, subject: str) -> bool:
    return bool(
        row
        and row.get("holder_type") == audience
        and row.get("employee") == (subject if audience == WORKER else None)
        and row.get("driver") == (subject if audience == DRIVER else None)
    )


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def get_config(entry: str) -> dict:
    _resolve_identity(entry)
    if not web_push.is_configured():
        return {"enabled": False}
    return {"enabled": True, "vapid_public_key": web_push.public_key()}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def save_subscription(
    entry: str,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None = None,
) -> dict:
    audience, subject = _resolve_identity(entry)
    if not web_push.is_configured():
        frappe.throw(_("Background notifications are not configured."), frappe.ValidationError)

    endpoint = _clean(endpoint, 2048, _("Notification endpoint"))
    p256dh = _clean(p256dh, 256, _("Notification key"))
    auth = _clean(auth, 256, _("Notification secret"))
    user_agent = (user_agent or "").strip()[:500]
    if not web_push.is_allowed_push_endpoint(endpoint):
        frappe.throw(_("The notification endpoint is not an approved push service."), frappe.ValidationError)

    existing = frappe.db.get_value(
        _SUBSCRIPTION_DOCTYPE,
        {"endpoint": endpoint},
        ["name", "holder_type", "employee", "driver"],
        as_dict=True,
    )
    if existing and not _belongs_to(existing, audience, subject):
        frappe.throw(_("This notification device belongs to another portal holder."), frappe.PermissionError)

    doc = frappe.get_doc(_SUBSCRIPTION_DOCTYPE, existing.name) if existing else frappe.new_doc(_SUBSCRIPTION_DOCTYPE)
    doc.update(
        {
            "holder_type": audience,
            "employee": subject if audience == WORKER else None,
            "driver": subject if audience == DRIVER else None,
            "endpoint": endpoint,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": user_agent,
            "enabled": 1,
            "last_seen": frappe.utils.now_datetime(),
        }
    )
    doc.save(ignore_permissions=True)
    return {"subscribed": True}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def delete_subscription(entry: str, endpoint: str) -> dict:
    audience, subject = _resolve_identity(entry)
    endpoint = _clean(endpoint, 2048, _("Notification endpoint"))
    row = frappe.db.get_value(
        _SUBSCRIPTION_DOCTYPE,
        {"endpoint": endpoint},
        ["name", "holder_type", "employee", "driver"],
        as_dict=True,
    )
    if not row:
        return {"subscribed": False}
    if not _belongs_to(row, audience, subject):
        frappe.throw(_("This notification device belongs to another portal holder."), frappe.PermissionError)
    frappe.db.set_value(_SUBSCRIPTION_DOCTYPE, row.name, "enabled", 0)
    return {"subscribed": False}
