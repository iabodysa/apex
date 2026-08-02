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

# The two the token system actually implements. frontend_shared/tokens.css defines a light
# block, whose default identity is the afmco alias, and a dark block — nothing else. Four more
# names were offered here for years and every one of them rendered as the light default, so the
# screen promised a choice the portals could not make.
THEME_SLUGS = {
    "AFMCO": "afmco",
    "Dark": "dark",
}
# Retired names, kept only so a record saved under one can be recognised and repointed rather
# than throwing on validate. Nothing reads them as a theme.
RETIRED_THEMES = ("Frappe Standard", "Gemini", "Atelier", "Creative")

DEFAULT_THEME = "AFMCO"
DEFAULT_SLUG = "afmco"


class DriverPortalTheme(Document):
    def validate(self):
        # A site saved under one of the four retired names would otherwise be unable to save at
        # all — the value is already stored, so throwing traps the operator on a screen whose
        # only invalid field is one the app itself wrote. Repoint and say so.
        if self.theme in RETIRED_THEMES:
            frappe.msgprint(
                _("The {0} theme was retired; this portal now uses {1}.").format(
                    self.theme, DEFAULT_THEME
                ),
                indicator="orange",
            )
            self.theme = DEFAULT_THEME

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
