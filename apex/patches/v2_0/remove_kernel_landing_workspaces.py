# Copyright (c) 2026, AFMCO and contributors
"""Remove the retired kernel landing Workspaces My Work + Launchpad.

Workspace consolidation folded the Launchpad onboarding / settings / logs into the
Habitat root, added the personal Action Inbox shortcut onto the Habitat + Salis roots,
and relocated Backend Engines into the Habitat module (hidden). The two Apex Core
landing Workspaces are gone from disk; migrate is import-only and never reconciles a
deleted is_standard JSON, so it leaves the orphaned Workspace rows -- and their child
Link / Shortcut / Number Card / Chart rows -- behind, plus any User whose
``default_workspace`` still points at one.

post_model_sync: deletes DB rows only (no JSON left to read). Fully guarded and
idempotent -- a no-op on a fresh install or any site that never had these Workspaces.
"""

from __future__ import annotations

import frappe

_RETIRED = ("My Work", "Launchpad")


def execute() -> None:
    if frappe.db.has_column("User", "default_workspace"):
        for name in _RETIRED:
            frappe.db.set_value(
                "User",
                {"default_workspace": name},
                "default_workspace",
                "",
                update_modified=False,
            )

    for name in _RETIRED:
        if frappe.db.exists("Workspace", name):
            frappe.delete_doc("Workspace", name, ignore_permissions=True, force=True)  # audit-ok

    if frappe.db.exists("Workspace", "Backend Engines"):
        frappe.db.set_value(
            "Workspace", "Backend Engines", "is_hidden", 1, update_modified=False
        )

    frappe.db.commit()
