# Copyright (c) 2026, afmcoltd
"""Seed portal appearance defaults. Install-safe and idempotent.

``seed_salis_portal_theme`` reaches here only from hooks.py's ``after_install``/
``after_migrate``, so the acting user is always Administrator, who already carries
every permission (frappe/permissions.py:107,273,506).

A Single needs a seeder rather than a patch: ``seed_all`` covers the habitat and salis
data files and not this record, and a stamped patch never runs again, so a patch would
set these values on existing sites and on no new one.

Only BLANK fields are filled, so an administrator's later choice is never overwritten,
and a site whose DocType has not migrated yet is skipped rather than raising.
"""

import frappe


DOCTYPE = "Salis Settings"

DEFAULTS = {
    "show_brand": 1,
}


def seed_salis_portal_theme():
    """Fill blank appearance defaults. Return field names set on this call."""
    if not frappe.db.exists("DocType", DOCTYPE):
        return []

    settings = frappe.get_single(DOCTYPE)
    stored = frappe.db.get_singles_dict(DOCTYPE)
    filled = []
    for field, value in DEFAULTS.items():
        if settings.meta.has_field(field) and field not in stored:
            settings.set(field, value)
            filled.append(field)
    if filled:
        settings.save()
    return filled
