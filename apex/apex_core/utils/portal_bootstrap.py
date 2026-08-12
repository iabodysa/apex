# Copyright (c) 2026, Apex contributors

"""Shared bootstrap for the www portal host pages.

Portal host pages share a non-secret client contract, appearance projection, and the
Guest -> /login redirect. Page-specific authentication and authorization stay local.

This module does not validate credentials, grant capabilities, or mint CSRF tokens.
"""

from __future__ import annotations

import re

import frappe

from apex.salis.doctype.driver_portal_theme.driver_portal_theme import (
    get_portal_appearance,
)


PORTAL_PUBLIC_PATHS = {
    "worker": frozenset({"/masar/"}),
    "driver": frozenset({"/driver/"}),
    "transport-supervisor": frozenset({"/masar-supervisor"}),
    "fleet-self-service": frozenset({"/fleet"}),
    "fleet-operations": frozenset({"/fleet-os"}),
    "housing": frozenset({"/housing", "/safety"}),
}

_PORTAL_TITLES = {
    "worker": "أبكس | مسار",
    "driver": "أبكس | السائق",
    "transport-supervisor": "أبكس | إشراف مسار",
    "fleet-self-service": "أبكس | سلس",
    "fleet-operations": "أبكس | تشغيل سلس",
    "housing": "أبكس | السكن",
}

_PWA_META = {
    "worker": {
        "manifest_url": "/assets/apex/worker_portal/manifest.webmanifest",
        "apple_icon_url": (
            "/assets/apex/worker_portal/icons/masar-apple-touch-icon-180.png"
        ),
        "service_worker_url": "/masar-sw.min.js",
        "service_worker_scope": "/masar/",
    },
    "driver": {
        "manifest_url": "/assets/apex/worker_portal/driver.webmanifest",
        "apple_icon_url": (
            "/assets/apex/worker_portal/icons/driver-apple-touch-icon-180.png"
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
    """Return the non-secret state shared by every Apex portal shell."""
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


def build_portal_shell_meta(*, entry: str, public_path: str) -> dict:
    """Return presentation and PWA metadata without authorization state."""
    _validate_entry_path(entry, public_path)
    pwa = _PWA_META.get(entry, {})
    return {
        "title": _PORTAL_TITLES[entry],
        "canonical_path": public_path,
        "manifest_url": pwa.get("manifest_url"),
        "apple_icon_url": pwa.get("apple_icon_url"),
        "theme_color": "#00844E",
        "service_worker_url": pwa.get("service_worker_url"),
        "service_worker_scope": pwa.get("service_worker_scope"),
    }


def apply_portal_appearance(context) -> None:
    """Project portal brand overrides onto ``context``.

	Sets ``portal_accent`` / ``portal_logo`` / ``portal_show_brand``.
	"""
    appearance = get_portal_appearance()
    context.portal_accent = appearance["accent"]
    context.portal_logo = appearance["logo"]
    context.portal_show_brand = appearance["show_brand"]


def guest_redirect(path: str) -> None:
    """Redirect an unauthenticated visitor to /login then back to ``path``.

	Raises ``frappe.Redirect`` for Guest; a no-op for a logged-in user, so a page
	can call this unconditionally at the top of ``get_context``.
	"""
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=" + path
        raise frappe.Redirect
