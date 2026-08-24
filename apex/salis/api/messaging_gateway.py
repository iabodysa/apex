# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.integrations.utils import make_post_request

from apex.apex_core.utils.phone import normalize_phone
from apex.apex_core.utils.portal_identity import (
    WORKER,
    credential_delivery_destination,
)

_SETTINGS = "Salis Settings"

_MAX_MESSAGE_LEN = 1000


def _gateway_config() -> dict | None:
    s = frappe.get_single(_SETTINGS)
    if not s.get("messaging_gateway_enabled"):
        return None
    url = (s.get("messaging_gateway_url") or "").strip()
    api_key = s.get_password("messaging_gateway_api_key", raise_exception=False)
    if not url or not api_key:
        return None
    return {
        "url": url,
        "api_key": api_key,
        "channel": s.get("messaging_gateway_channel") or "WhatsApp",
        "sender_id": (s.get("messaging_gateway_sender_id") or "").strip() or None,
    }


def is_configured() -> bool:
    return _gateway_config() is not None


def _post_to_gateway(cfg: dict, to: str, message: str, channel: str) -> dict:
    payload = {"to": to, "message": message, "channel": channel}
    if cfg.get("sender_id"):
        payload["sender_id"] = cfg["sender_id"]
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    try:
        response = make_post_request(cfg["url"], headers=headers, json=payload)
        return {"sent": True, "channel": channel, "response": response}
    except Exception:
        frappe.log_error(title="Messaging gateway send failed")
        return {"sent": False, "channel": channel, "error": "gateway_error"}


def send_message(to: str, message: str, channel: str | None = None) -> dict:
    try:
        cfg = _gateway_config()
    except Exception:
        frappe.log_error(title="Messaging gateway config read failed")
        return {"sent": False, "reason": "not_configured"}
    if not cfg:
        frappe.logger("messaging_gateway").info("send skipped: gateway not configured")
        return {"sent": False, "reason": "not_configured"}

    try:
        phone = normalize_phone(to)
        if not phone:
            return {"sent": False, "reason": "no_phone"}

        message = (message or "").strip()
        if not message:
            return {"sent": False, "reason": "empty_message"}
        if len(message) > _MAX_MESSAGE_LEN:
            message = message[: _MAX_MESSAGE_LEN - 1] + "…"

        return _post_to_gateway(cfg, phone, message, (channel or cfg["channel"]))
    except Exception:
        frappe.log_error(title="Messaging gateway send failed")
        return {"sent": False, "error": "gateway_error"}


def enqueue_message(to: str, message: str, channel: str | None = None) -> dict:
    if not is_configured():
        frappe.logger("messaging_gateway").info("enqueue skipped: gateway not configured")
        return {"queued": False, "reason": "not_configured"}
    if not normalize_phone(to):
        return {"queued": False, "reason": "no_phone"}
    frappe.enqueue(
        "apex.salis.api.messaging_gateway.send_message",
        queue="short",
        enqueue_after_commit=True,
        to=to,
        message=message,
        channel=channel,
    )
    return {"queued": True}


def _masar_link_message(employee_name: str | None, link: str, extra: str | None = None) -> str:
    name = (employee_name or "").strip()
    greeting = _("Hello {0},").format(name) if name else _("Hello,")
    body = _("Open your personal worker portal (Masar): {0}").format(link)
    parts = [greeting, body]
    if extra:
        parts.append(extra.strip())
    return "\n".join(parts)


def send_masar_link(
    employee: str,
    link: str,
    phone: str | None = None,
    status_line: str | None = None,
    channel: str | None = None,
) -> dict:
    to = credential_delivery_destination(WORKER, employee, requested=phone)
    employee_name = frappe.db.get_value("Employee", employee, "employee_name")
    message = _masar_link_message(employee_name, link, status_line)
    return enqueue_message(to, message, channel=channel)


@frappe.whitelist(methods=["POST"])
def send_test_message(to: str, message: str | None = None) -> dict:
    frappe.has_permission(_SETTINGS, "write", throw=True)
    if not is_configured():
        frappe.throw(
            _("The messaging gateway is not enabled or is missing its URL/API key. Configure it in Salis Settings first.")
        )
    message = (message or "").strip() or _("Apex messaging gateway test message.")
    return send_message(to, message)
