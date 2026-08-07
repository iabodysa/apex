# Copyright (c) 2026, afmcoltd
"""Driver Web Push sender (settings-driven, no-op until VAPID is configured).

Delivers a short background push — a trip assigned, a fuel request approved — to a
driver's device through the Web Push protocol, so a driver with the app closed still
gets the alert. Mirrors ``messaging_gateway``: the app ships NO keys; delivery needs
a VAPID key pair the operator provisions and stores in **Salis Settings**. Until
the toggle is on AND a private key is present, every send is a safe, logged no-op,
so callers fire-and-forget without guarding "is push set up yet".

The actual encrypted-payload delivery (RFC 8291) needs the ``pywebpush`` package,
which is intentionally NOT bundled. ``_deliver`` is the single integration seam: it
no-ops cleanly when the library is absent, so the scaffold installs and runs with no
new dependency, and the owner adds ``pywebpush`` only when enabling push for real.

The VAPID private key and a subscription's endpoint/auth secret are secrets — read
from Settings/the subscription DocType at send time, used, and discarded; never
logged, never returned to a client."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

import frappe

_SETTINGS = "Salis Settings"

_MAX_BODY_LEN = 300

_PUSH_HOST_EXACT = frozenset(
    {
        "fcm.googleapis.com",
        "updates.push.services.mozilla.com",
    }
)
_PUSH_HOST_SUFFIX = (
    ".push.apple.com",
    ".notify.windows.com",
)


def is_allowed_push_endpoint(endpoint: str | None) -> bool:
    """True only for an ``https://`` URL whose host is a known push provider.

    The single SSRF gate for the web-push endpoint, shared by the save-time check and
    the deliver-time re-check. Requires HTTPS (a push endpoint always is) and an exact
    or dotted-suffix host match against the provider allowlist. A literal IP host is
    refused outright — no provider is an IP, and this blocks loopback/link-local/private
    /metadata targets (127/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1) up front.
    Suffix matches require a real subdomain label so ``evil-push.apple.com`` (no dot
    boundary) and ``fcm.googleapis.com.evil.com`` (exact set) are both rejected."""
    if not endpoint:
        return False
    parts = urlparse(endpoint.strip())
    if parts.scheme != "https" or not parts.hostname:
        return False
    host = parts.hostname.lower()
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    if host in _PUSH_HOST_EXACT:
        return True
    return any(host.endswith(suffix) and len(host) > len(suffix) for suffix in _PUSH_HOST_SUFFIX)


def _vapid_config() -> dict | None:
    """The live VAPID config, or None when push is off/unconfigured.

	Reads the Single fresh (no cache) so an operator enabling push or rotating the
	key takes effect immediately. Returns None — the no-op signal — when the master
	toggle is off or the public/private key pair is missing, so every caller degrades
	to a logged no-op instead of erroring."""
    s = frappe.get_single(_SETTINGS)
    if not s.get("enable_web_push"):
        return None
    public_key = (s.get("web_push_vapid_public_key") or "").strip()
    private_key = s.get_password("web_push_vapid_private_key", raise_exception=False)
    if not public_key or not private_key:
        return None
    return {
        "public_key": public_key,
        "private_key": private_key,
        "subject": (s.get("web_push_vapid_subject") or "").strip() or "mailto:admin@example.com",
    }


def is_configured() -> bool:
    """True when push is enabled AND a VAPID key pair is present.

	Lets the SPA bootstrap decide whether to offer the opt-in at all (and exposes the
	PUBLIC key only — never the private one) without leaking the secret."""
    return _vapid_config() is not None


def public_key() -> str | None:
    """The VAPID PUBLIC key for the SPA to subscribe with, or None when unconfigured.

	The public key is safe to hand to the browser (it is what ``pushManager.subscribe``
	needs as ``applicationServerKey``); the private key never leaves the server."""
    cfg = _vapid_config()
    return cfg["public_key"] if cfg else None


def _active_subscriptions(driver: str) -> list[dict]:
    """Enabled push subscriptions for ``driver`` (endpoint + keys), newest first.

	Reads the device secrets needed to deliver one push. Endpoint-scoped to the one
	driver; returns an empty list when the driver has opted in on no device."""
    return frappe.get_all(
        "Driver Push Subscription",
        filters={"driver": driver, "enabled": 1},
        fields=["name", "endpoint", "p256dh"],
        order_by="modified desc",
    )


def _deliver(cfg: dict, subscription: dict, payload: str) -> bool:
    """Deliver one encrypted push to one subscription. The single integration seam.

	No-ops cleanly (returns False) when ``pywebpush`` is not installed, so the
	scaffold runs with no new dependency. When the library IS present this sends the
	RFC-8291 encrypted payload with the VAPID claims. A 404/410 from the push service
	means the browser dropped the subscription, so the stale row is disabled. Any other
	transport error is logged (title only — never the payload, endpoint, or key) and
	swallowed, so one dead device never breaks a fan-out."""
    if not is_allowed_push_endpoint(subscription.get("endpoint")):
        frappe.db.set_value("Driver Push Subscription", subscription["name"], "enabled", 0)
        frappe.logger("web_push").info("send skipped: endpoint host not allowlisted")
        return False

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        frappe.logger("web_push").info("send skipped: pywebpush not installed")
        return False

    auth = frappe.utils.password.get_decrypted_password(
        "Driver Push Subscription", subscription["name"], "auth", raise_exception=False
    )
    sub_info = {
        "endpoint": subscription["endpoint"],
        "keys": {"p256dh": subscription.get("p256dh"), "auth": auth},
    }
    try:
        webpush(
            subscription_info=sub_info,
            data=payload,
            vapid_private_key=cfg["private_key"],
            vapid_claims={"sub": cfg["subject"]},
        )
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            frappe.db.set_value("Driver Push Subscription", subscription["name"], "enabled", 0)
        else:
            frappe.log_error(title="Web push delivery failed")
        return False
    except Exception:
        frappe.log_error(title="Web push delivery failed")
        return False


def send_to_driver(driver: str, title: str, body: str, url: str | None = None) -> dict:
    """Send one background push to every device a driver opted in on.

	The single high-level send. Returns ``{"sent": int, ...}`` and NEVER raises on a
	configuration or transport problem:

	  * push off/unconfigured  -> ``{"sent": 0, "reason": "not_configured"}``
	    (a logged no-op, not an error);
	  * driver has no devices  -> ``{"sent": 0, "reason": "no_subscription"}``.

	``url`` is an in-app path (e.g. ``/driver?tab=trips``) the SW opens when the driver
	taps the notification. Secrets are read here, used, and discarded."""
    try:
        cfg = _vapid_config()
    except Exception:
        frappe.log_error(title="Web push config read failed")
        return {"sent": 0, "reason": "not_configured"}
    if not cfg:
        frappe.logger("web_push").info("send skipped: web push not configured")
        return {"sent": 0, "reason": "not_configured"}

    try:
        subs = _active_subscriptions(driver)
        if not subs:
            return {"sent": 0, "reason": "no_subscription"}

        body = (body or "").strip()
        if len(body) > _MAX_BODY_LEN:
            body = body[: _MAX_BODY_LEN - 1] + "…"
        payload = frappe.as_json({"title": title, "body": body, "url": url or "/driver"})

        sent = sum(1 for sub in subs if _deliver(cfg, sub, payload))
        return {"sent": sent, "devices": len(subs)}
    except Exception:
        frappe.log_error(title="Web push send failed")
        return {"sent": 0, "reason": "send_failed"}


def enqueue_to_driver(driver: str, title: str, body: str, url: str | None = None) -> dict:
    """Queue a push so delivery happens off the request cycle.

	Preferred entry point for controller callers: a slow or unreachable push service
	must never block a document save. Returns immediately; when push is not configured
	it does not even enqueue (a no-op), so the worker is never woken for nothing."""
    if not is_configured():
        frappe.logger("web_push").info("enqueue skipped: web push not configured")
        return {"queued": False, "reason": "not_configured"}
    frappe.enqueue(
        "apex.salis.api.web_push.send_to_driver",
        queue="short",
        driver=driver,
        title=title,
        body=body,
        url=url,
    )
    return {"queued": True}
