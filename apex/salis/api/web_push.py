# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import base64
import ipaddress
from urllib.parse import urlparse

import frappe
from frappe import _

from apex.apex_core.utils.portal_identity import DRIVER, WORKER

_SETTINGS = "Salis Settings"
_SUBSCRIPTION_DOCTYPE = "Portal Push Subscription"
_MAX_BODY_LEN = 300
_PUSH_HOST_EXACT = frozenset({"fcm.googleapis.com", "updates.push.services.mozilla.com"})
_PUSH_HOST_SUFFIX = (".push.apple.com", ".notify.windows.com")
_SUBJECT_FIELDS = {WORKER: "employee", DRIVER: "driver"}
_SUBJECT_DOCTYPES = {WORKER: "Employee", DRIVER: "Salis Driver"}


def _subject_field(audience: str) -> str:
    try:
        return _SUBJECT_FIELDS[audience]
    except KeyError:
        frappe.throw(_("Portal notification audience must be Worker or Driver."), frappe.ValidationError)


def is_allowed_push_endpoint(endpoint: str | None) -> bool:
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
    return host in _PUSH_HOST_EXACT or any(
        host.endswith(suffix) and len(host) > len(suffix) for suffix in _PUSH_HOST_SUFFIX
    )


def is_p256_point(key: str) -> bool:
    padded = key.strip().replace("-", "+").replace("_", "/")
    padded += "=" * ((4 - len(padded) % 4) % 4)
    try:
        point = base64.b64decode(padded)
    except (ValueError, TypeError):
        return False
    return len(point) == 65 and point[0] == 4


def _vapid_config() -> dict | None:
    settings = frappe.get_single(_SETTINGS)
    if not settings.get("enable_web_push"):
        return None
    public = (settings.get("web_push_vapid_public_key") or "").strip()
    private = settings.get_password("web_push_vapid_private_key", raise_exception=False)
    if not public or not private or not is_p256_point(public):
        return None
    return {
        "public_key": public,
        "private_key": private,
        "subject": (settings.get("web_push_vapid_subject") or "").strip()
        or "mailto:admin@example.com",
    }


def is_configured() -> bool:
    return _vapid_config() is not None


def public_key() -> str | None:
    config = _vapid_config()
    return config["public_key"] if config else None


def _has_live_token(audience: str, subject: str) -> bool:
    fieldname = _subject_field(audience)
    if frappe.db.get_value(_SUBJECT_DOCTYPES[audience], subject, "status") != "Active":
        return False
    return bool(
        frappe.get_all(
            "Masar Worker Token",
            filters={
                "holder_type": audience,
                fieldname: subject,
                "enabled": 1,
                "expires_on": [">", frappe.utils.now_datetime()],
            },
            pluck="name",
            limit=1,
        )
    )


def _active_subscriptions(audience: str, subject: str) -> list[dict]:
    if not _has_live_token(audience, subject):
        return []
    return frappe.get_all(
        _SUBSCRIPTION_DOCTYPE,
        filters={
            "holder_type": audience,
            _subject_field(audience): subject,
            "enabled": 1,
        },
        fields=["name", "endpoint", "p256dh"],
        order_by="modified desc",
    )


def disable_subject_subscriptions(audience: str, subject: str) -> int:
    if not subject:
        return 0
    rows = frappe.get_all(
        _SUBSCRIPTION_DOCTYPE,
        filters={
            "holder_type": audience,
            _subject_field(audience): subject,
            "enabled": 1,
        },
        pluck="name",
    )
    for name in rows:
        frappe.db.set_value(_SUBSCRIPTION_DOCTYPE, name, "enabled", 0, update_modified=False)
    return len(rows)


def _deliver(config: dict, subscription: dict, payload: str) -> bool:
    if not is_allowed_push_endpoint(subscription.get("endpoint")):
        frappe.db.set_value(_SUBSCRIPTION_DOCTYPE, subscription["name"], "enabled", 0)
        return False

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        frappe.logger("web_push").info("send skipped: pywebpush not installed")
        return False

    auth = frappe.utils.password.get_decrypted_password(
        _SUBSCRIPTION_DOCTYPE,
        subscription["name"],
        "auth",
        raise_exception=False,
    )
    try:
        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {"p256dh": subscription.get("p256dh"), "auth": auth},
            },
            data=payload,
            vapid_private_key=config["private_key"],
            vapid_claims={"sub": config["subject"]},
        )
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            frappe.db.set_value(_SUBSCRIPTION_DOCTYPE, subscription["name"], "enabled", 0)
        else:
            frappe.log_error(title="Web push delivery failed")
        return False
    except Exception:
        frappe.log_error(title="Web push delivery failed")
        return False


def send_to_subject(
    audience: str,
    subject: str,
    title: str,
    body: str,
    url: str | None = None,
) -> dict:
    try:
        config = _vapid_config()
    except Exception:
        frappe.log_error(title="Web push config read failed")
        return {"sent": 0, "reason": "not_configured"}
    if not config:
        return {"sent": 0, "reason": "not_configured"}

    try:
        subscriptions = _active_subscriptions(audience, subject)
        if not subscriptions:
            return {"sent": 0, "reason": "no_subscription"}
        clean_body = (body or "").strip()
        if len(clean_body) > _MAX_BODY_LEN:
            clean_body = clean_body[: _MAX_BODY_LEN - 1] + "…"
        payload = frappe.as_json(
            {
                "title": title,
                "body": clean_body,
                "url": url or ("/masar/" if audience == WORKER else "/driver/"),
            }
        )
        sent = sum(1 for row in subscriptions if _deliver(config, row, payload))
        return {"sent": sent, "devices": len(subscriptions)}
    except Exception:
        frappe.log_error(title="Web push send failed")
        return {"sent": 0, "reason": "send_failed"}


def enqueue_to_subject(
    audience: str,
    subject: str,
    title: str,
    body: str,
    url: str | None = None,
) -> dict:
    if not is_configured():
        return {"queued": False, "reason": "not_configured"}
    frappe.enqueue(
        "apex.salis.api.web_push.send_to_subject",
        queue="short",
        enqueue_after_commit=True,
        audience=audience,
        subject=subject,
        title=title,
        body=body,
        url=url,
    )
    return {"queued": True}


def enqueue_boarding_event(
    event: str,
    dispatch_trip: str,
    *,
    driver: str | None = None,
    employees: list[str] | None = None,
    payload: dict | None = None,
) -> int:
    workers = list(dict.fromkeys(employee for employee in (employees or []) if employee))
    route = f"/driver/#/route/{dispatch_trip}"
    worker_route = "/masar/#/transport"
    targets = []

    if event == "wait_request" and driver:
        targets.append((DRIVER, driver, "طلب انتظار", "أحد الركاب طلب منك الانتظار قبل المغادرة.", route))
    elif event == "boarding_confirmed" and driver:
        targets.append((DRIVER, driver, "تم الصعود", "تحدّثت قائمة الركاب بعد صعود أحدهم.", route))
    elif event == "boarding_unmarked":
        targets.extend(
            (WORKER, employee, "تحديث حالة الصعود", "أعاد السائق حالتك إلى بانتظار الصعود.", worker_route)
            for employee in workers
        )
    elif event == "boarding_arrived":
        targets.extend(
            (WORKER, employee, "وصلت الحافلة", "السائق عند نقطة تجمعك الآن.", worker_route)
            for employee in workers
        )
    elif event == "boarding_update":
        targets.extend(
            (WORKER, employee, "السائق بانتظارك", "جهز نفسك واتجه إلى نقطة التجمع.", worker_route)
            for employee in workers
        )
    elif event == "driver_trip_update" and (payload or {}).get("status") == "Started":
        targets.extend(
            (WORKER, employee, "بدأت رحلتك", "تحركت الحافلة؛ تابع وقت الوصول من التطبيق.", worker_route)
            for employee in workers
        )

    for target in targets:
        enqueue_to_subject(*target)
    return len(targets)
