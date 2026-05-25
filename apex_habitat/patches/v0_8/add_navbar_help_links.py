"""Add Apex Habitat quick links to the navbar Help dropdown.

Navbar Settings is a global Single, so we must NOT ship it as a fixture (that
would overwrite the customer's own navbar on every migrate). Instead this patch
reads the existing Single and APPENDS our help links only if absent — additive
and idempotent, never clobbering existing items.
"""

import frappe

_LINKS = [
    {"item_label": "Apex Habitat — Command Center", "item_type": "Route", "route": "/app/habitat"},
    {"item_label": "Apex Habitat — Setup", "item_type": "Route", "route": "/app/setup"},
]


def execute():
    try:
        if not frappe.db.exists("DocType", "Navbar Settings"):
            return
        settings = frappe.get_single("Navbar Settings")
        existing = {row.item_label for row in settings.help_dropdown}
        changed = False
        for link in _LINKS:
            if link["item_label"] in existing:
                continue
            settings.append("help_dropdown", {
                "item_label": link["item_label"],
                "item_type": link["item_type"],
                "route": link["route"],
                "is_standard": 0,
            })
            changed = True
        if changed:
            settings.save(ignore_permissions=True)  # audit-ok
            frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="add_navbar_help_links failed",
            message=frappe.get_traceback(),
        )
