import frappe

# Two workspace merges shipped as new records:
#   Habitat: "Upkeep" + "Safety"  -> "Facilities"
#   Salis:   "Workers" + "Fuel"   -> "Movement"  ("Fleet" stays separate)
# The new Workspaces are imported from the app's fixtures on migrate, but the
# four merged-away records remain orphaned in the DB and would keep showing in
# the sidebar. Remove them and load the two replacements. Idempotent and
# existence-guarded; a no-op on fresh installs (nothing stale to delete) and on
# re-run (records already gone / already reloaded).

OBSOLETE = ("Upkeep", "Safety", "Workers", "Fuel")


def execute():
    if not frappe.db.exists("DocType", "Workspace"):
        return

    for name in OBSOLETE:
        if frappe.db.exists("Workspace", name):
            try:
                frappe.delete_doc("Workspace", name, ignore_missing=True, force=True)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(title="merge_facilities_movement_workspaces: " + str(name))

    frappe.reload_doc("habitat", "workspace", "facilities")
    frappe.reload_doc("salis", "workspace", "movement")

    frappe.db.commit()
    frappe.clear_cache()
