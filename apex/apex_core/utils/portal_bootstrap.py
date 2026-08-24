# Copyright (c) 2026, Apex contributors


from __future__ import annotations

import hashlib
import hmac
import re

import frappe
from frappe import _lt
from frappe.sessions import get_csrf_token
from frappe.translate import get_translations_from_csv
from frappe.utils import cint, get_system_timezone
from frappe.utils.jinja_globals import is_rtl
from frappe.utils.password import get_encryption_key

PORTAL_PUBLIC_PATHS = {
    "worker": frozenset({"/masar/"}),
    "driver": frozenset({"/driver/"}),
    "transport-supervisor": frozenset({"/masar-supervisor"}),
    "fleet-self-service": frozenset({"/fleet"}),
    "fleet-operations": frozenset({"/fleet-os"}),
    "housing": frozenset({"/housing", "/safety"}),
}

_PORTAL_TITLES = {
    "worker": _lt("Apex | Masar"),
    "driver": _lt("Apex | Driver"),
    "transport-supervisor": _lt("Apex | Masar supervision"),
    "fleet-self-service": _lt("Apex | Salis"),
    "fleet-operations": _lt("Apex | Salis operations"),
    "housing": _lt("Apex | Housing"),
}

_PWA_META = {
    "worker": {
        "manifest_url": "/assets/apex/apex_portal/manifests/masar.webmanifest",
        "apple_icon_url": (
            "/assets/apex/apex_portal/icons/masar-apple-touch-icon-180.png"
        ),
        "service_worker_url": "/masar-sw.min.js",
        "service_worker_scope": "/masar/",
    },
    "driver": {
        "manifest_url": "/assets/apex/apex_portal/manifests/driver.webmanifest",
        "apple_icon_url": (
            "/assets/apex/apex_portal/icons/driver-apple-touch-icon-180.png"
        ),
        "service_worker_url": "/driver-sw.min.js",
        "service_worker_scope": "/driver/",
    },
}

_OPAQUE_SUBJECT_SCOPE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

def _validate_entry_path(entry: str, public_path: str) -> None:
    if public_path not in PORTAL_PUBLIC_PATHS.get(entry, ()):
        raise ValueError(f"Unknown Apex portal entry/path pair: {entry!r}, {public_path!r}")

def build_portal_bootstrap(
    *,
    entry: str,
    public_path: str,
    initial_route: str,
    capabilities,
    site_name: str,
    socketio_port,
    async_enabled: bool,
    language: str,
    subject_scope: str,
) -> dict:
    _validate_entry_path(entry, public_path)
    if not isinstance(capabilities, (list, tuple, set, frozenset)) or any(
        not isinstance(capability, str) or not capability
        for capability in capabilities
    ):
        raise ValueError("Portal capabilities must be non-empty strings")
    if not isinstance(subject_scope, str) or not _OPAQUE_SUBJECT_SCOPE.fullmatch(
        subject_scope
    ):
        raise ValueError("Portal subject_scope must be opaque")

    return {
        "entry": entry,
        "public_path": public_path,
        "initial_route": initial_route,
        "capabilities": sorted(set(capabilities)),
        "site_name": site_name,
        "socketio_port": socketio_port,
        "async_enabled": bool(async_enabled),
        "language": language,
        "subject_scope": subject_scope,
    }

_DEFAULT_THEME_COLOR = "#00844E"
_SEED_COLOR = re.compile(r"\A#[0-9A-Fa-f]{3,8}\Z")
_APPEARANCE_FIELDS = ("accent_color", "brand_logo", "show_brand")

def portal_language() -> str:
    language = getattr(frappe.local, "lang", None) or frappe.db.get_default("lang") or "en"
    frappe.local.lang = language
    return language

def portal_seed_color(raw: str | None) -> str:
    candidate = (raw or "").strip()
    return candidate if _SEED_COLOR.fullmatch(candidate) else ""

def build_portal_shell_meta(*, entry: str, public_path: str) -> dict:
    _validate_entry_path(entry, public_path)
    pwa = _PWA_META.get(entry, {})
    appearance = frappe.db.get_value(
        "Salis Settings", "Salis Settings", _APPEARANCE_FIELDS, as_dict=True
    ) or frappe._dict()
    seed = portal_seed_color(appearance.get("accent_color"))
    show_brand = bool(cint(appearance.get("show_brand")))
    language = portal_language()
    return {
        "title": str(_PORTAL_TITLES[entry]),
        "language": language,
        "direction": "rtl" if is_rtl() else "ltr",
        "time_zone": get_system_timezone(),
        "canonical_path": public_path,
        "manifest_url": pwa.get("manifest_url"),
        "apple_icon_url": pwa.get("apple_icon_url"),
        "theme_color": seed or _DEFAULT_THEME_COLOR,
        "seed_color": seed,
        "service_worker_url": pwa.get("service_worker_url"),
        "service_worker_scope": pwa.get("service_worker_scope"),
        "show_brand": show_brand,
        "brand_logo": (appearance.get("brand_logo") or "") if show_brand else "",
    }

def opaque_subject_scope(*, entry: str, subject: str | None) -> str:
    _validate_entry_path(entry, next(iter(PORTAL_PUBLIC_PATHS[entry])))
    material = "\x1f".join(
        (frappe.local.site or "site", entry, subject or "unauthenticated")
    ).encode()
    digest = hmac.new(get_encryption_key().encode(), material, hashlib.sha256).hexdigest()
    return f"scope_{digest[:24]}"

def publish_portal_context(
    context,
    *,
    entry: str,
    public_path: str,
    initial_route: str,
    capabilities,
    subject: str | None,
):
    conf = frappe.get_site_config()
    context.no_cache = 1
    context.csrf_token = get_csrf_token()
    language = portal_language()
    context.portal_messages = get_translations_from_csv(language, "apex")
    context.shell_meta = build_portal_shell_meta(
        entry=entry,
        public_path=public_path,
    )
    context.boot = {
        "apex_portal": build_portal_bootstrap(
            entry=entry,
            public_path=public_path,
            initial_route=initial_route,
            capabilities=capabilities,
            site_name=frappe.local.site,
            socketio_port=cint(conf.get("socketio_port")) or 9000,
            async_enabled=not cint(conf.get("disable_async")),
            language=language,
            subject_scope=opaque_subject_scope(entry=entry, subject=subject),
        )
    }
    return context

def guest_redirect(path: str) -> None:
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=" + path
        raise frappe.Redirect
