import frappe

# TEMPORARY SAFEGUARD (GitHub #97) — PRUNE once every deployed site is confirmed on the
# v15-correct Web Form fixture (tracked in tabPatch Log).
#
# On an upgrade FROM AN OLD VERSION a Web Form could arrive without its `route`: the v14
# helper that used to set it — frappe.website.doctype.web_form.web_form.make_route_to_web_form
# — was REMOVED in Frappe v15, so a deployment step still calling it crashes with an
# AttributeError (issue #97). apex_habitat never calls that helper and its Web Form fixture
# already carries route="qr-request"; this patch is pure precaution. It idempotently ensures
# the Web Form keeps its route + stays published so routing works natively and the removed
# helper is never needed. It is a no-op when the route is already set, and never clobbers a
# deliberately-different route.

WEB_FORM = "accommodation-resident-request"
ROUTE = "qr-request"


def execute():
    # Not present yet (e.g. a fresh DB before the standard fixture imports) → nothing to
    # heal; the fixture import sets the route itself.
    if not frappe.db.exists("Web Form", WEB_FORM):
        return

    current = frappe.db.get_value("Web Form", WEB_FORM, ["route", "published"], as_dict=True) or {}
    updates = {}
    if not current.get("route"):
        updates["route"] = ROUTE  # only when missing — never override a custom route
    if not current.get("published"):
        updates["published"] = 1
    if updates:
        frappe.db.set_value("Web Form", WEB_FORM, updates)
        frappe.db.commit()
