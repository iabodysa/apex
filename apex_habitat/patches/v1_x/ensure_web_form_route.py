import frappe

# [#rzordp]
# [#jbkgyo]
# [#od1fgp]
# [#d732sr]
# [#c2knfs]
# [#ev4y71]
# [#jef3t4]
# [#p0eke1]
# [#5w6qh7]
# [#2t51z6]
# [#mcrsfb]

WEB_FORM = "accommodation-resident-request"
ROUTE = "qr-request"


def execute():
    # [#2zmmj0]
    # [#15lepy]
    if not frappe.db.exists("Web Form", WEB_FORM):
        return

    current = frappe.db.get_value("Web Form", WEB_FORM, ["route", "published"], as_dict=True) or {}
    updates = {}
    if not current.get("route"):
        updates["route"] = ROUTE  # [#gzrs5p]
    if not current.get("published"):
        updates["published"] = 1
    if updates:
        frappe.db.set_value("Web Form", WEB_FORM, updates)
        frappe.db.commit()
