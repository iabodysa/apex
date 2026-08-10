# Copyright (c) 2026, afmcoltd
"""Masar portal appearance controller.

Single DocType that controls the optional brand mark and accent used by portal
shells. Apex ships one light color system; this record does not select a theme.

Only display configuration lives here — no fleet data and no financial impact.
"""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.document import Document

_CSS_COLOR_RE = re.compile(
    r"""^(?:
		\#[0-9A-Fa-f]{3,8}                      # #rgb / #rgba / #rrggbb / #rrggbbaa
		| (?:rgb|rgba|hsl|hsla)\(               # functional notation …
			[0-9.,%\s/deg]+ \)                  # … digits, %, commas, slash, deg, ws only
		| [A-Za-z]+                             # a CSS colour keyword (red, transparent, …)
	)$""",
    re.VERBOSE,
)

_BRAND_LOGO_RE = re.compile(r"^/files/[^\"'<>\s]+$")

class DriverPortalTheme(Document):
    def validate(self):
        """Validate the optional accent color and brand logo."""
        accent = (self.accent_color or "").strip()
        if accent and not _CSS_COLOR_RE.match(accent):
            frappe.throw(_("Accent Color must be a valid CSS colour."))

        logo = (self.brand_logo or "").strip()
        if logo and not _BRAND_LOGO_RE.match(logo):
            frappe.throw(_("Brand Logo must be an uploaded file (a /files/ path)."))


def get_portal_appearance() -> dict:
    """Resolve the portal's appearance settings for the web renderer.

	Returns a plain dict with safe defaults so ``www/driver.py`` never has to
	branch on a missing Single or a half-configured record:

    - ``accent``     : optional accent colour override (hex) or "".
	- ``logo``       : optional brand-logo URL or "".
	- ``show_brand`` : bool, default True.
	"""
    accent = ""
    logo = ""
    show_brand = True

    if frappe.db.exists("DocType", "Driver Portal Theme"):
        settings = frappe.get_cached_doc("Driver Portal Theme")
        accent = (settings.accent_color or "").strip()
        logo = (settings.brand_logo or "").strip()
        show_brand = bool(settings.show_brand) if settings.get("show_brand") is not None else True

    return {
        "accent": accent,
        "logo": logo,
        "show_brand": show_brand,
    }
