"""Repoint navbar Help-dropdown links that targeted the now-deleted admin workspaces.

The Habitat "Setup", Habitat "Console" and Salis "Salis Setup" workspaces were
merged into the single "Apex Core" workspace and their records deleted
(see consolidate_admin_workspaces_into_apex_core). The v0_8 add_navbar_help_links
patch had already seeded an "Apex Habitat — Setup" Help-dropdown item routed to
``/app/setup`` on installed sites, so that menu entry now dead-ends.

Navbar Settings is a global Single (never shipped as a fixture, or migrate would
clobber the customer's navbar). This patch reads the Single in place and rewrites
ONLY help-dropdown rows whose route points at a deleted workspace, repointing them
to ``/app/apex-core``. It never adds, removes or touches any other navbar item.

ONE-TIME (prune-eligible once every deployed site has run it). Idempotent: rows
are matched on the exact stale routes, so a re-run finds nothing to change; a
no-op on a fresh install (add_navbar_help_links now seeds /app/apex-core directly).
"""

import frappe

# Routes of the three deleted admin workspaces -> the consolidated hub.
_STALE_ROUTES = {"/app/setup", "/app/console", "/app/salis-setup"}
_TARGET = "/app/apex-core"


def execute():
    if not frappe.db.exists("DocType", "Navbar Settings"):
        return
    try:
        settings = frappe.get_single("Navbar Settings")
        changed = False
        for row in settings.help_dropdown:
            if row.route in _STALE_ROUTES:
                row.route = _TARGET
                changed = True
        if changed:
            settings.save(ignore_permissions=True)  # audit-ok: repoint dead workspace routes
            frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="fix_navbar_routes_to_apex_core failed",
            message=frappe.get_traceback(),
        )
