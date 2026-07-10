# Copyright (c) 2026, AFMCO and contributors
"""Rename DocType 'Habitat City' → 'City'.

DELETE THIS PATCH FILE on or after 2026-06-24 (30 days after deploy).
Once all production sites have been migrated, this patch is no longer needed
and the file can be safely removed from the repository. The patch runner
tracks executed patches by name, so removing the file after migration is safe.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Habitat City"):
        # [#1vr3sz]
        return

    # Guard the rename target: if "City" already exists (a prior partial run, or a
    # parallel slice created it), renaming onto it would collide. The source DocType
    # is left in place for manual reconciliation rather than force-merged blindly.
    if frappe.db.exists("DocType", "City"):
        return

    frappe.rename_doc(
        "DocType",
        "Habitat City",
        "City",
        force=True,
    )
