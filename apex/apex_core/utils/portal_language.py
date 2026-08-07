# Copyright (c) 2026, afmcoltd
"""Render a portal page in the language the page itself declares.

`_()` translates into `frappe.local.lang`, which frappe resolves from the SESSION user
(their `User.language`, else System Settings). The portal shells declare `lang="ar"
dir="rtl"` in their own markup, so on a site whose default is English the access-denied
screen painted English sentences inside an RTL box — and an RTL container puts the Latin
full stop at the START of the line, which is how ".This page is for the fleet team"
reached a user.

Calling this from a portal's ``get_context`` makes the two agree: the page says Arabic,
so the strings resolve Arabic, for every visitor regardless of their desk preference.
"""

import frappe


def render_in_arabic() -> None:
    """Set the request's translation language to Arabic for the rest of this render."""
    frappe.local.lang = "ar"
