"""Rename DocType 'Habitat City' → 'City'.

DELETE THIS PATCH FILE on or after 2026-06-24 (30 days after deploy).
Once all production sites have been migrated, this patch is no longer needed
and the file can be safely removed from the repository. The patch runner
tracks executed patches by name, so removing the file after migration is safe.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Habitat City"):
        # Already renamed or never existed — nothing to do
        return

    frappe.rename_doc(
        "DocType",
        "Habitat City",
        "City",
        force=True,
    )
    frappe.db.commit()
