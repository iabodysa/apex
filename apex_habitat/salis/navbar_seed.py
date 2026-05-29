"""Seed Salis (movement/fleet) quick links into the desk navbar Help dropdown.

Mirrors the Habitat pattern (``patches/v0_8/add_navbar_help_links.py``): Navbar
Settings is a global Single, so we must NOT ship it as a fixture (that would
overwrite the customer's own navbar on every migrate). Instead this reads the
existing Single and APPENDS our help links only if absent — additive and
idempotent, never clobbering existing items.

The seed logic lives here (single source of truth) and is reused by the app's
``after_install`` / ``after_migrate`` hooks, exactly like the other Salis seeds
(notifications, kanban, assignment rules). A fresh install gets the links
immediately while already-installed sites pick them up on migrate. Re-running is
safe: each link is keyed on its label and added only when missing.

Routes are verified against the shipped artifacts:
- Salis workspace ``salis/workspace/salis/salis.json`` (name "Salis") -> /app/salis
- Salis Dispatch Board page ``salis/page/salis_dispatch_board`` (name
  "salis-dispatch-board") -> /app/salis-dispatch-board
"""

import frappe

# Same shape as Habitat's _LINKS: label-keyed, additive, is_standard = 0 so the
# customer can remove them. Workspace + key operational page reachable in one click;
# native Ctrl+/ keyboard shortcuts continue to surface these routes unchanged.
_LINKS = [
    {"item_label": "Apex Salis — Movement & Fleet", "item_type": "Route", "route": "/app/salis"},
    {"item_label": "Apex Salis — Dispatch Board", "item_type": "Route", "route": "/app/salis-dispatch-board"},
]


def seed_salis_navbar_help_links():
    """Append the Salis Help-dropdown links if absent. Safe to re-run."""
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
            title="seed_salis_navbar_help_links failed",
            message=frappe.get_traceback(),
        )
