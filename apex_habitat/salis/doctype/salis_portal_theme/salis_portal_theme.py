"""Salis Portal Theme controller.

Single DocType that drives the look and feel of the Salis Driver Portal (the
mobile web app served at ``/driver``). The values here are read by
``www/driver.py`` at render time and projected onto the page as a ``data-theme``
attribute plus an optional ``--c-accent`` override, so the entire token-based
stylesheet re-skins without rebuilding the SPA.

Only display configuration lives here — no fleet data and no financial impact.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

# Map each admin-facing theme label to the slug consumed by the portal's
# ``data-theme`` attribute / CSS token scopes. Kept here as the single source of
# truth so the controller and the web renderer never drift.
THEME_SLUGS = {
	"AFMCO": "afmco",
	"Frappe Standard": "frappe",
	"Dark": "dark",
}

DEFAULT_THEME = "AFMCO"
DEFAULT_SLUG = "afmco"


class SalisPortalTheme(Document):
	def validate(self):
		# Defensive: the Select already constrains this, but guard against a
		# direct API write smuggling in an unknown value (which would otherwise
		# silently fall back to the default slug at render time).
		if self.theme and self.theme not in THEME_SLUGS:
			frappe.throw(_("Invalid portal theme: {0}").format(self.theme))


def get_portal_appearance() -> dict:
	"""Resolve the portal's appearance settings for the web renderer.

	Returns a plain dict with safe defaults so ``www/driver.py`` never has to
	branch on a missing Single or a half-configured record:

	- ``theme``      : token slug ("afmco" | "frappe" | "dark"), default "afmco".
	- ``accent``     : optional accent colour override (hex) or "".
	- ``logo``       : optional brand-logo URL or "".
	- ``show_brand`` : bool, default True.
	"""
	theme_slug = DEFAULT_SLUG
	accent = ""
	logo = ""
	show_brand = True

	# Skip-missing: the DocType may not be migrated yet on this site. Fall back
	# to the flat AFMCO default rather than raising inside page rendering.
	if frappe.db.exists("DocType", "Salis Portal Theme"):
		settings = frappe.get_cached_doc("Salis Portal Theme")
		theme_slug = THEME_SLUGS.get(settings.theme or DEFAULT_THEME, DEFAULT_SLUG)
		accent = (settings.accent_color or "").strip()
		logo = (settings.brand_logo or "").strip()
		# show_brand defaults to on; only an explicit 0 hides the brand.
		show_brand = bool(settings.show_brand) if settings.get("show_brand") is not None else True

	return {
		"theme": theme_slug,
		"accent": accent,
		"logo": logo,
		"show_brand": show_brand,
	}
