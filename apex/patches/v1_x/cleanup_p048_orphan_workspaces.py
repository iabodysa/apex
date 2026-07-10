# Copyright (c) 2026, AFMCO and contributors
"""Remove the Workspaces + Module Onboardings orphaned by the P-048 14->8 merge.

The 14->8 workspace consolidation deleted the source JSON for several Workspaces and
two Module Onboardings. `migrate` is import-only (it never reconciles a deleted JSON),
so on already-installed sites the old DB rows survive as orphans -- they keep rendering
in the desk switcher and shadow the merged set. Only a fresh install drops them; this
post_model_sync patch removes the stale rows by name.

Two of the deleted Workspaces had names that collide CASE-INSENSITIVELY with a current
live workspace ("Costs" vs the new "costs", "Fleet" vs the live "fleet"). Under the
default case-insensitive collation the JSON import already upserted those rows into the
live workspace, so they are NOT orphans and MUST NOT be deleted. The guard below skips
any orphan whose name matches a live (still-shipped) workspace case-insensitively, so
the patch is safe regardless of DB collation.

Idempotent: re-running finds nothing to delete. No-op on fresh installs.
"""

import frappe

# [#p048cw]

# [#qsfsd8]
ORPHAN_WORKSPACES = [
    "Apex Home",
    "Habitat Hub",
    "Fleet Operations",
    "Compliance",
    "Rentals",
]

# [#j8jr35]
ORPHAN_ONBOARDINGS = [
    "Fleet Operations Go-Live",
    "Salis Go-Live",
]


def execute():
    live = {w.lower() for w in _shipped_workspace_names()}
    for name in ORPHAN_WORKSPACES:
        # [#lbzzw7]
        if name.lower() in live:
            continue
        if frappe.db.exists("Workspace", name):
            frappe.delete_doc("Workspace", name, force=True, ignore_permissions=True)  # audit-ok migration: system-context orphan cleanup

    for name in ORPHAN_ONBOARDINGS:
        if frappe.db.exists("Module Onboarding", name):
            frappe.delete_doc("Module Onboarding", name, force=True, ignore_permissions=True)  # audit-ok migration: system-context orphan cleanup

    frappe.db.commit()


def _shipped_workspace_names():
    # [#52mj2j]
    return [
        "Launchpad",
        "My Work",
        "Habitat",
        "Salis",
        "Custody",
        "Housing",
        "Safety",
        "fleet",
        "Masar",
        "Compliance and Rentals",
        "Costs and Leasing",
    ]
