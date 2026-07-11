# Copyright (c) 2026, AFMCO and contributors
"""Rename DocType 'Freelance' → 'Freelancer' (T-033 adjective→noun; moved to Logistay).

ONE-TIME: prune once every deployed site has run it (tracked in tabPatch Log).
Runs pre_model_sync so the rename lands BEFORE the Logistay freelancer.json
import — otherwise sync would create a second, empty 'Freelancer' DocType and
the rename would collide. Record names (FRL-<serial>) are unchanged, so party
links stay valid.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Freelance"):
        # [#ef2j47]
        return

    # [#510oz9]
    if frappe.db.exists("DocType", "Freelancer"):
        return

    frappe.rename_doc(
        "DocType",
        "Freelance",
        "Freelancer",
        force=True,
    )
