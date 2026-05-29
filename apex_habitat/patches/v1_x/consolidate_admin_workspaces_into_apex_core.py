"""Consolidate the three admin/settings workspaces into "Apex Core".

The Habitat "Setup", Habitat "Console", and Salis "Salis Setup" workspaces were
merged into the single cross-module "Apex Core" config hub (their links,
shortcuts, number cards and roles were folded into Apex Core's shipped JSON) and
their fixture directories were removed.

Deleting a Workspace fixture file does NOT delete the persisted Workspace record:
migrate only imports/updates shipped files, it never removes a record whose file
disappeared. So on already-installed sites the three records would linger in the
desk sidebar. This patch deletes them.

ONE-TIME (prune-eligible once every deployed site has run it). Idempotent and
existence-guarded: a no-op on a fresh install (the records are never shipped) and
on any site that has already run it.
"""

import frappe

_ORPHANED = ("Setup", "Console", "Salis Setup")


def execute():
    # Guard: the Workspace DocType must exist before we query/delete its records.
    if not frappe.db.exists("DocType", "Workspace"):
        return

    removed_any = False
    for name in _ORPHANED:
        if not frappe.db.exists("Workspace", name):
            # Already gone (fresh install or re-run) - skip safely.
            continue
        try:
            frappe.delete_doc(
                "Workspace", name, ignore_missing=True, force=True
            )  # audit-ok: consolidated into Apex Core
            removed_any = True
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title="consolidate_admin_workspaces_into_apex_core: " + str(name),
                message=frappe.get_traceback(),
            )

    if removed_any:
        frappe.db.commit()
        frappe.clear_cache()
