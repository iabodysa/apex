# Copyright (c) 2026, AFMCO and contributors
import frappe

from apex.salis.doctype.driver_portal_theme.driver_portal_theme import (
    DEFAULT_THEME,
    RETIRED_THEMES,
)


def execute():
    """Move a portal still set to a retired theme onto the default.

    Four of the six names the screen used to offer were never implemented by the token system:
    every one of them rendered as the light default anyway. Removing them from the Select does
    not change what is already stored, and a stored value outside the options list reaches the
    portal as-is, so the row has to be rewritten rather than left to the next manual save.

    Driver Portal Theme is a Single, so the value lives in tabSingles and there is exactly one.
    """
    if not frappe.db.exists("DocType", "Driver Portal Theme"):
        return

    current = frappe.db.get_single_value("Driver Portal Theme", "theme")
    if current in RETIRED_THEMES:
        frappe.db.set_single_value("Driver Portal Theme", "theme", DEFAULT_THEME)
