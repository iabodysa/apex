# Copyright (c) 2026, AFMCO and contributors
"""Rename two Workspaces whose name != title so name == title (P-099).

The desk router keys public workspaces by ``slug(name)`` but the sidebar links
by ``slug(title)``. When a workspace's name slugs differently from its title the
sidebar link 404s on open: ``costs`` (title "Costs and Leasing") and
``compliance_rentals`` (title "Compliance and Rentals") both threw "Page not
found" when opened from the desk. Renaming the DB row so name == title (the
ERPNext convention, e.g. "Financial Reports") makes the sidebar link resolve.

post_model_sync: the JSON sync may already have created the new-named row. If so,
drop the stale old-named row; otherwise rename in place so deployed sites carry
across. Idempotent and order-safe; no-op on fresh installs (only the new name
exists). The parent_page hierarchy ("Operations"/"Habitat" parents) is restored
by the shipped JSON on migrate.
"""

import frappe

_RENAMES = [
    ("costs", "Costs and Leasing"),
    ("compliance_rentals", "Compliance and Rentals"),
]


def execute():
    for old, new in _RENAMES:
        if not frappe.db.exists("Workspace", old):
            continue
        if frappe.db.exists("Workspace", new):
            frappe.delete_doc("Workspace", old, force=True, ignore_permissions=True)  # audit-ok migration: system-context workspace cleanup
        else:
            frappe.rename_doc("Workspace", old, new, force=True, ignore_permissions=True)  # audit-ok migration: system-context workspace rename
    frappe.clear_cache()
