# Copyright (c) 2026, afmcoltd

"""Shared bootstrap for the www portal host pages.

Portal host pages share appearance projection and the Guest -> /login redirect.
These helpers keep that boilerplate in one place while page-specific security stays
local. Apex uses one light color system; appearance only controls brand overrides.

Deliberately NOT here (kept local to each page): the CSRF-token mint, the masar
``?w`` token charset guard, per-page role gates, and fleet's Socket.IO config —
those differ per page and carry their own security comments.
"""

from __future__ import annotations

import frappe

from apex.salis.doctype.driver_portal_theme.driver_portal_theme import (
    get_portal_appearance,
)


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
