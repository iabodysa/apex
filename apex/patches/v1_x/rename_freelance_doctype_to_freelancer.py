# Copyright (c) 2026, AFMCO and contributors
"""Rename DocType 'Freelance' → 'Freelancer' (T-033 adjective→noun; moved to Logistay).

ONE-TIME: prune once every deployed site has run it (tracked in tabPatch Log).
Runs pre_model_sync so the rename lands BEFORE the Logistay freelancer.json
import — otherwise sync would create a second, empty 'Freelancer' DocType and
the rename would collide. Record names (FRL-#####) are unchanged, so party
links stay valid.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Freelance"):
        # Fresh site (JSON already ships Freelancer) or already renamed.
        return

    # Guard the rename target: renaming onto an existing 'Freelancer' would
    # collide. Leave the source for manual reconciliation, never force-merge.
    if frappe.db.exists("DocType", "Freelancer"):
        return

    frappe.rename_doc(
        "DocType",
        "Freelance",
        "Freelancer",
        force=True,
    )
