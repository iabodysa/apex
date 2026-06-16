import frappe

# [#97y67m]

STALE_WORKSPACES = ["Habitat", "Accommodation", "Facilities", "Apex Core"]


def execute():
    for name in STALE_WORKSPACES:
        if frappe.db.exists("Workspace", name):
            frappe.delete_doc("Workspace", name, force=True, ignore_permissions=True)
    frappe.db.commit()
