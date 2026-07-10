# Copyright (c) 2026, AFMCO and contributors
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

    # ASSERT the route is byte-identical (B9 / V2 cutover red-line). The QR posters and
    # deep links hardcode `/qr-request`; the B7 DocType rename must leave this route
    # untouched. Fail CLOSED on any drift so a cutover that silently repointed the form
    # is caught at migrate time instead of shipping dead QR codes to the field.
    final_route = frappe.db.get_value("Web Form", WEB_FORM, "route")
    if final_route != ROUTE:
        frappe.throw(
            "Web Form '{0}' route is '{1}', expected '{2}': the QR-request route must stay "
            "byte-identical across the rename (QR posters/deep links depend on it).".format(
                WEB_FORM, final_route, ROUTE
            )
        )
