# Copyright (c) 2026, AFMCO and contributors
"""Outbound WhatsApp / SMS gateway sender (settings-driven, provider-agnostic).

Pushes short worker-facing messages — a personal Masar link, a ride departure,
or a request-resolved notice — to a worker's phone through a generic HTTP gateway
the operator configures in **Apex Integration Settings**. The app bundles no
provider: it POSTs a small JSON body to one configurable URL, so any provider
(an official WhatsApp Business API host, an SMS aggregator, Twilio, or a thin
middleware) is wired without code changes.

Credentials live ONLY in the Settings DocType (the API key in a Password field,
read at send time) — never in code, never logged. When the gateway is disabled or
unconfigured every send is a safe, logged no-op, so calling code never has to
guard for "is messaging set up yet".
"""

from __future__ import annotations

import frappe
from frappe import _

# Settings home for the gateway config. One Single, read fresh per send so an
# operator toggle takes effect without a restart.
_SETTINGS = "Apex Integration Settings"

# Max body length handed to the gateway — keeps a single SMS-class message sane
# regardless of provider; longer text is truncated rather than rejected.
_MAX_MESSAGE_LEN = 1000


def _gateway_config() -> dict | None:
    """The live gateway config, or None when messaging is off/unconfigured.

    Reads the Single fresh (no cache) so an operator enabling the gateway or
    rotating the key takes effect immediately. Returns None — the no-op signal —
    when the master switch is off or the URL/key is missing, so every caller
    degrades to a logged no-op instead of erroring."""
    s = frappe.get_single(_SETTINGS)
    if not s.get("messaging_gateway_enabled"):
        return None
    url = (s.get("messaging_gateway_url") or "").strip()
    # get_password decrypts the stored secret; never inline a key in code.
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
    """True when the gateway is enabled AND has a URL + API key.

    Lets a UI offer a "send via WhatsApp/SMS" action only when it will actually
    do something, without exposing the credential."""
    return _gateway_config() is not None


def _normalize_phone(phone) -> str | None:
    """Trim a phone to digits and a single leading ``+``, or None when empty.

    Provider-agnostic light cleanup (strips spaces/dashes/parens a record may
    carry); the gateway/provider does final validation and country defaulting."""
    phone = (phone or "").strip()
    if not phone:
        return None
    cleaned = "".join(ch for ch in phone if ch.isdigit())
    return ("+" + cleaned) if phone.startswith("+") else cleaned or None


def _post_to_gateway(cfg: dict, to: str, message: str, channel: str) -> dict:
    """POST one message to the configured gateway and return a result dict.

    Sends ``{to, message, channel, sender_id}`` with the API key as a Bearer
    token, using Frappe's native HTTP helper. Any transport/HTTP error is caught,
    logged (WITHOUT the body or key), and returned as ``sent=False`` so a send
    failure never bubbles into the caller's flow."""
    from frappe.integrations.utils import make_post_request

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
        # Log title only — never the message body, phone, or key.
        frappe.log_error(title="Messaging gateway send failed")
        return {"sent": False, "channel": channel, "error": "gateway_error"}


def send_message(to: str, message: str, channel: str | None = None) -> dict:
    """Send one WhatsApp/SMS message through the configured gateway.

    The single low-level send. Returns ``{"sent": bool, ...}`` and NEVER raises
    on a configuration or transport problem:

      * gateway off/unconfigured -> ``{"sent": False, "reason": "not_configured"}``
        (a logged no-op, not an error);
      * no/blank phone           -> ``{"sent": False, "reason": "no_phone"}``;
      * transport/HTTP failure   -> ``{"sent": False, "error": "gateway_error"}``.

    Credentials are read from Settings here, used for this call, and discarded;
    nothing is persisted or logged."""
    # Reading the Settings Single can raise on a transient DB error; this is also
    # an enqueue() target, so honour the "never raises" contract in the worker too.
    try:
        cfg = _gateway_config()
    except Exception:
        frappe.log_error(title="Messaging gateway config read failed")
        return {"sent": False, "reason": "not_configured"}
    if not cfg:
        # No-op by design: callers fire-and-forget without guarding setup.
        frappe.logger("messaging_gateway").info("send skipped: gateway not configured")
        return {"sent": False, "reason": "not_configured"}

    phone = _normalize_phone(to)
    if not phone:
        return {"sent": False, "reason": "no_phone"}

    message = (message or "").strip()
    if not message:
        return {"sent": False, "reason": "empty_message"}
    if len(message) > _MAX_MESSAGE_LEN:
        message = message[: _MAX_MESSAGE_LEN - 1] + "…"

    return _post_to_gateway(cfg, phone, message, (channel or cfg["channel"]))


def enqueue_message(to: str, message: str, channel: str | None = None) -> dict:
    """Queue a message so the send happens off the request cycle.

    Preferred entry point for UI/controller callers: a slow or unreachable
    gateway must never block the desk action or a document save. Returns
    immediately with ``{"queued": bool, "reason": ...}``; when the gateway is not
    configured it does not even enqueue (a no-op), so the background worker is
    never woken for nothing."""
    if not is_configured():
        frappe.logger("messaging_gateway").info("enqueue skipped: gateway not configured")
        return {"queued": False, "reason": "not_configured"}
    if not _normalize_phone(to):
        return {"queued": False, "reason": "no_phone"}
    frappe.enqueue(
        "apex_habitat.salis.api.messaging_gateway.send_message",
        queue="short",
        to=to,
        message=message,
        channel=channel,
    )
    return {"queued": True}


def _masar_link_message(employee_name: str | None, link: str, extra: str | None = None) -> str:
    """Compose the worker-facing Masar-link message body.

    A greeting + the personal link, optionally followed by a status line (a ride
    departure or a resolved request). English source string; the worker-facing
    localization rides on the app's translation layer."""
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
    """Send a worker their personal Masar link (+ optional status) to their phone.

    The convenience used by the arrivals/worker surfaces: composes the link
    message (and an optional ``status_line`` such as a ride departure or a
    resolved request) and queues it. ``phone`` may be passed by the caller (it
    already has it from the link-issuer); when omitted it is read from the
    Employee record server-side. Returns the ``enqueue_message`` result; a no-op
    when the gateway is off or no phone is on file."""
    to = phone or frappe.db.get_value("Employee", employee, "cell_number")
    employee_name = frappe.db.get_value("Employee", employee, "employee_name")
    message = _masar_link_message(employee_name, link, status_line)
    return enqueue_message(to, message, channel=channel)


@frappe.whitelist(methods=["POST"])
def send_test_message(to: str, message: str | None = None) -> dict:
    """Operator self-test: send one message NOW with the stored credentials.

    Permission-gated on write to Apex Integration Settings (only an operator who
    can see the gateway config may fire a test). Sends synchronously so the
    operator gets the real ``{"sent": ...}`` verdict back, confirming the URL +
    key work end to end. No worker data is exposed — the operator supplies the
    destination."""
    frappe.has_permission(_SETTINGS, "write", throw=True)
    if not is_configured():
        frappe.throw(
            _("The messaging gateway is not enabled or is missing its URL/API key. Configure it in Apex Integration Settings first.")
        )
    message = (message or "").strip() or _("Apex messaging gateway test message.")
    return send_message(to, message)
