"""Seed Salis Portal Theme default values.

Idempotent and install-safe: only fills BLANK fields (never clobbers an admin's
later choice), skips gracefully if the DocType is not yet migrated, and wraps
everything so it can never fail an install/migrate. The portal defaults to the
flat AFMCO brand theme with branding shown.
"""

import frappe

DEFAULTS = {
    "theme": "AFMCO",
    "show_brand": 1,
}


def execute():
    try:
        # Skip-missing: module/doctype not migrated yet on this site.
        if not frappe.db.exists("DocType", "Salis Portal Theme"):
            return

        settings = frappe.get_single("Salis Portal Theme")
        changed = False

        # Only fill blanks — respect any value an admin already set.
        for field, value in DEFAULTS.items():
            if settings.meta.has_field(field) and not settings.get(field):
                settings.set(field, value)
                changed = True

        if changed:
            settings.save(ignore_permissions=True)  # audit-ok
            frappe.db.commit()
    except Exception:
        # A seed must NEVER crash install/migrate — log and continue.
        frappe.db.rollback()
        frappe.log_error(
            title="seed_salis_portal_theme failed",
            message=frappe.get_traceback(),
        )
