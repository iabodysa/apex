import frappe

# [#p9d94s]
# [#od1fgp]
# [#5brg1h]
# [#8c8zel]
# [#n2p2hc]
# [#kr8fga]
# [#od1fgp]
# [#jmi9ph]
# [#rwgzut]
# [#hi7lca]
# [#ddavb1]
# [#8b46on]
# [#od1fgp]
# [#o6uq9a]

STALE_WORKSPACES = ["Habitat", "Accommodation", "Facilities", "Apex Core"]


def execute():
    for name in STALE_WORKSPACES:
        if frappe.db.exists("Workspace", name):
            frappe.delete_doc("Workspace", name, force=True, ignore_permissions=True)
    frappe.db.commit()
