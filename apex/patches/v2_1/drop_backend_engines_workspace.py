import frappe


def execute():
    """Remove the Backend Engines workspace, whose content moved to Apex Core.

    A standard workspace that leaves the app is not removed by migrate — the record stays behind
    and keeps rendering an empty page in the sidebar, because sync only imports what it finds on
    disk. Its links now live under the Apex Core workspace, which is a child of the Apex root.
    """
    if not frappe.db.exists("Workspace", "Backend Engines"):
        return

    frappe.delete_doc("Workspace", "Backend Engines", force=True, ignore_permissions=True)
