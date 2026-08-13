import frappe
from frappe.model.rename_doc import rename_doc


OLD_DOCTYPE = "Driver Push Subscription"
NEW_DOCTYPE = "Portal Push Subscription"


def execute():
    if not frappe.db.exists("DocType", OLD_DOCTYPE):
        return
    if frappe.db.exists("DocType", NEW_DOCTYPE):
        frappe.throw(f"Both {OLD_DOCTYPE} and {NEW_DOCTYPE} exist; migration stopped.")
    rename_doc(
        "DocType",
        OLD_DOCTYPE,
        NEW_DOCTYPE,
        force=True,
        validate=False,
        show_alert=False,
        rebuild_search=False,
    )
