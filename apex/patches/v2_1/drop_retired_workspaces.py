import frappe

# Backend Engines became Apex Core; Compliance and Rentals folded into Salis alongside the
# short-lived Masar and Operations pages.
RETIRED = ("Backend Engines", "Compliance and Rentals", "Masar", "Operations")


def execute():
    """Remove the workspaces whose links moved elsewhere.

    A standard workspace that leaves the app is not removed by migrate — the record stays behind
    and keeps rendering an empty page in the sidebar, because sync only imports what it finds on
    disk.
    """
    for name in RETIRED:
        if frappe.db.exists("Workspace", name):
            frappe.delete_doc("Workspace", name, force=True, ignore_permissions=True)
