# Copyright (c) 2026, AFMCO and contributors
# [#pb1bza]

"""Shared bootstrap for the www portal host pages (driver / masar / fleet / safety).

The four ``www/*.py`` host pages each rendered the SAME two bits of boilerplate:
the Salis Portal Theme appearance projection, and the Guest -> /login redirect.
These helpers hold that single copy so the pages stay identical where they should.

Deliberately NOT here (kept local to each page): the CSRF-token mint, the masar
``?w`` token charset guard, per-page role gates, and fleet's Socket.IO config —
those differ per page and carry their own security comments.
"""

from __future__ import annotations

import frappe

from apex_habitat.salis.doctype.salis_portal_theme.salis_portal_theme import (
	get_portal_appearance,
)


def apply_portal_appearance(context) -> None:
	"""Project the Salis Portal Theme onto ``context`` (theme + brand overrides).

	Sets ``portal_theme`` / ``portal_accent`` / ``portal_logo`` /
	``portal_show_brand`` so every portal shell re-skins from the one Single.
	"""
	appearance = get_portal_appearance()
	context.portal_theme = appearance["theme"]
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
