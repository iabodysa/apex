import frappe

# The Salis area workspaces were renamed to short labels (Workers/Fleet/Fuel/
# Rentals/Compliance/Setup). Renaming a Workspace `name` imports a new record on
# migrate but leaves the old long-named record orphaned, so the sidebar shows
# duplicates. Remove any Salis-module Workspace whose name is not in the shipped
# set. Idempotent and guarded; safe on fresh installs (nothing stale to remove).

SHIPPED = {"Salis", "Workers", "Fleet", "Fuel", "Rentals", "Compliance"}


def execute():
    if not frappe.db.exists("DocType", "Workspace"):
        return
    for name in frappe.get_all("Workspace", filters={"module": "Salis"}, pluck="name"):
        if name in SHIPPED:
            continue
        try:
            frappe.delete_doc("Workspace", name, ignore_missing=True, force=True)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="cleanup_renamed_salis_workspaces: " + str(name))
    frappe.db.commit()
    frappe.clear_cache()
