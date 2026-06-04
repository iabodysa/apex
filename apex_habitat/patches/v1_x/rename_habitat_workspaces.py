import frappe

# Patch: remove stale workspace records left behind after the v1.50.8 canonical rename.
#
# Frappe sync_fixtures creates a NEW record when the workspace JSON `name` changes
# (the old record stays because the old filename/key is no longer in the fixture set).
# This patch deletes only the four old workspace names; the renamed replacements were
# already created by migrate's fixture sync.
#
# Old name          → New canonical name
# Habitat           → Habitat Hub
# Accommodation     → Housing
# Facilities        → Safety
# Apex Core         → Launchpad
#
# Idempotent: skips records that were already deleted.

STALE_WORKSPACES = ["Habitat", "Accommodation", "Facilities", "Apex Core"]


def execute():
    for name in STALE_WORKSPACES:
        if frappe.db.exists("Workspace", name):
            frappe.delete_doc("Workspace", name, force=True, ignore_permissions=True)
    frappe.db.commit()
