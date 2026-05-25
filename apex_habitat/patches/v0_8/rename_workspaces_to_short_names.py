"""Rename the Habitat workspaces so each record's `name` equals its short `title`.

Frappe v15 keys the client workspace route table by slug(name) (router.js), while
the sidebar links by slug(title). With name != title (long name, short title) the
title-slug URL (e.g. /app/habitat) was not found and fell through to a Page lookup
-> 404. Renaming name -> title makes the route resolve. Children reference the
parent by its title ("Habitat"), which is unchanged, so parent_page stays valid.
Idempotent.
"""

import frappe

_RENAMES = {
    "Operations Command Center": "Habitat",
    "Accommodation Lifecycle": "Accommodation",
    "Maintenance & Remediation": "Upkeep",
    "Safety & Compliance": "Safety",
    "Custody & Asset Control": "Custody",
    "Lease, Utilities & Cost Control": "Costs",
    "Habitat System Administration": "Console",
}


def execute():
    for old, new in _RENAMES.items():
        if not frappe.db.exists("Workspace", old):
            continue
        if frappe.db.exists("Workspace", new):
            # Target already exists (re-run or sync created it) — drop the stale old one.
            frappe.delete_doc("Workspace", old, force=True, ignore_permissions=True)  # audit-ok
            continue
        frappe.rename_doc("Workspace", old, new, force=True)
    # Children nest by parent title "Habitat" (unchanged) — ensure none still point
    # at the old parent name.
    for name in frappe.get_all("Workspace", filters={"parent_page": "Operations Command Center"}, pluck="name"):
        frappe.db.set_value("Workspace", name, "parent_page", "Habitat", update_modified=False)
    frappe.db.commit()
