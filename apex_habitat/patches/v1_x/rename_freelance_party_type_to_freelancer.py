# Copyright (c) 2026, AFMCO and contributors
"""Rename Party Type record 'Freelance' → 'Freelancer'.

ONE-TIME: prune once every deployed site has run it (tracked in tabPatch Log).
Companion to rename_freelance_doctype_to_freelancer: the fixture now ships the
'Freelancer' Party Type, and rename_doc cascades party_type on existing
Journal / Payment Entry rows. Party record names (FRL-#####) are unchanged.
"""

import frappe


def execute():
    if not frappe.db.exists("Party Type", "Freelance"):
        # Fresh site (fixture already ships Freelancer) or already renamed.
        return

    # Guard the rename target: the fixture import may already have created
    # 'Freelancer'. Renaming onto it would collide; merge instead so existing
    # ledger rows keyed to 'Freelance' are re-pointed at the fixture row.
    if frappe.db.exists("Party Type", "Freelancer"):
        frappe.rename_doc(
            "Party Type",
            "Freelance",
            "Freelancer",
            merge=True,
            force=True,
        )
        return

    frappe.rename_doc(
        "Party Type",
        "Freelance",
        "Freelancer",
        force=True,
    )
