"""Remove the "Client Audit & Evidence" workspace after its content was merged
into "Safety & Compliance" (workspace consolidation). Idempotent."""

import frappe

OLD_WORKSPACE = "Client Audit & Evidence"


def execute():
    if not frappe.db.exists("Workspace", OLD_WORKSPACE):
        return
    try:
        frappe.delete_doc("Workspace", OLD_WORKSPACE, ignore_permissions=True, force=True)  # audit-ok
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="merge_client_audit_into_safety: failed to delete workspace",
            message=frappe.get_traceback(),
        )
