# Copyright (c) 2026, AFMCO and contributors
"""Salis Portal Theme controller.

Single DocType that drives the look and feel of the Salis Driver Portal (the
mobile web app served at ``/driver``). The values here are read by
``www/driver.py`` at render time and projected onto the page as a ``data-theme``
attribute plus an optional ``--c-accent`` override, so the entire token-based
stylesheet re-skins without rebuilding the SPA.

Only display configuration lives here — no fleet data and no financial impact.
"""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.document import Document

# [#5ys9co]
_CSS_COLOR_RE = re.compile(
    r"""^(?:
		\#[0-9A-Fa-f]{3,8}                      # #rgb / #rgba / #rrggbb / #rrggbbaa
		| (?:rgb|rgba|hsl|hsla)\(               # functional notation …
			[0-9.,%\s/deg]+ \)                  # … digits, %, commas, slash, deg, ws only
		| [A-Za-z]+                             # a CSS colour keyword (red, transparent, …)
	)$""",
    re.VERBOSE,
)

# [#lbu7js]
_BRAND_LOGO_RE = re.compile(r"^/files/[^\"'<>\s]+$")

# [#no616m]
THEME_SLUGS = {
    "AFMCO": "afmco",
    "Frappe Standard": "frappe",
    "Dark": "dark",
    "Gemini": "gemini",
    # [#psglhx]
    "Atelier": "atelier",
    # [#14ru3n]
    "Creative": "creative",
}

DEFAULT_THEME = "AFMCO"
DEFAULT_SLUG = "afmco"


class DriverPortalTheme(Document):
    def validate(self):
        # [#5ec5in]
        if self.theme and self.theme not in THEME_SLUGS:
            frappe.throw(_("Invalid portal theme: {0}").format(self.theme))

        # [#m8itbo]
        accent = (self.accent_color or "").strip()
        if accent and not _CSS_COLOR_RE.match(accent):
            frappe.throw(_("Accent Color must be a valid CSS colour."))

        # [#nv052n]
        logo = (self.brand_logo or "").strip()
        if logo and not _BRAND_LOGO_RE.match(logo):
            frappe.throw(_("Brand Logo must be an uploaded file (a /files/ path)."))


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

    # [#bs67p4]
    if frappe.db.exists("DocType", "Driver Portal Theme"):
        settings = frappe.get_cached_doc("Driver Portal Theme")
        theme_slug = THEME_SLUGS.get(settings.theme or DEFAULT_THEME, DEFAULT_SLUG)
        accent = (settings.accent_color or "").strip()
        logo = (settings.brand_logo or "").strip()
        # [#nga98z]
        show_brand = bool(settings.show_brand) if settings.get("show_brand") is not None else True

    return {
        "theme": theme_slug,
        "accent": accent,
        "logo": logo,
        "show_brand": show_brand,
    }
