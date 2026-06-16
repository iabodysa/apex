import frappe

# [#28bp9j]

WEB_FORM = "accommodation-resident-request"
ROUTE = "qr-request"


def execute():
    # [#9ofpfc]
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
