# Copyright (c) 2026, afmcoltd

import frappe


_LINKS = [
    {"item_label": "Apex Salis — Movement and Fleet", "item_type": "Route", "route": "/app/salis"},
    {"item_label": "Apex Salis — Dispatch Board", "item_type": "Route", "route": "/app/salis-dispatch-board"},
]


def seed_salis_navbar_help_links():
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
            settings.save()
            frappe.db.commit()
    except Exception:
        frappe.log_error(
            title="seed_salis_navbar_help_links failed",
            message=frappe.get_traceback(),
        )
