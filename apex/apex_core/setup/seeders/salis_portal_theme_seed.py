# Copyright (c) 2026, afmcoltd
"""Seed Driver Portal Theme defaults. Install-safe, idempotent, blank-fields-only.

This lived in ``patches/v1_0/seed_salis_portal_theme.py`` and nothing else re-created it:
no ``after_install`` step, no ``after_migrate`` step, and ``seed_all`` covers the habitat
and salis data files rather than this Single. A stamped patch never runs again, so the
patch was the only thing that had ever set these values — retiring it would have left
every new site's driver portal with no theme.

Only BLANK fields are filled, so an administrator's later choice is never overwritten,
and a site whose DocType has not migrated yet is skipped rather than raising.
"""

import frappe

DOCTYPE = "Driver Portal Theme"

DEFAULTS = {
    "theme": "AFMCO",
    "show_brand": 1,
}


def seed_salis_portal_theme():
    """Fill any blank theme default. Returns the fieldnames set on this call."""
    if not frappe.db.exists("DocType", DOCTYPE):
        return []

    settings = frappe.get_single(DOCTYPE)
    filled = []
    for field, value in DEFAULTS.items():
        if settings.meta.has_field(field) and not settings.get(field):
            settings.set(field, value)
            filled.append(field)
    if filled:
        settings.save(ignore_permissions=True)  # audit-ok
    return filled
