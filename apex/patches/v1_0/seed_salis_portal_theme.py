# Copyright (c) 2026, AFMCO and contributors
"""Seed Salis Portal Theme default values.

Idempotent and install-safe: only fills BLANK fields (never clobbers an admin's
later choice) and skips gracefully if the DocType is not yet migrated. The portal
defaults to the flat AFMCO brand theme with branding shown.
"""

import frappe

DEFAULTS = {
    "theme": "AFMCO",
    "show_brand": 1,
}


def execute():
    """No hook re-seeds this Single: nothing in ``after_migrate`` touches Driver Portal
    Theme, and a stamped patch never runs again, so a swallowed failure leaves the portal
    with no theme for good. A failure is therefore raised rather than logged."""
    if not frappe.db.exists("DocType", "Driver Portal Theme"):
        return

    settings = frappe.get_single("Driver Portal Theme")
    changed = False

    for field, value in DEFAULTS.items():
        if settings.meta.has_field(field) and not settings.get(field):
            settings.set(field, value)
            changed = True

    if changed:
        settings.save(ignore_permissions=True)  # audit-ok
        frappe.db.commit()
