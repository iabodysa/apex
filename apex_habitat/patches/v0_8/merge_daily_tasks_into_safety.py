"""Remove the "Daily & Scheduled Tasks" workspace after its content was merged
into "Safety & Compliance" (workspace consolidation 9 -> 8).

The Safety & Compliance workspace JSON now carries the daily-task shortcuts,
links, cards, chart and quick list, so the standalone workspace is redundant.
Idempotent: only deletes if the workspace still exists.
"""

import frappe

OLD_WORKSPACE = "Daily & Scheduled Tasks"


def execute():
    if not frappe.db.exists("Workspace", OLD_WORKSPACE):
        return
    try:
        frappe.delete_doc("Workspace", OLD_WORKSPACE, ignore_permissions=True, force=True)  # audit-ok
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="merge_daily_tasks_into_safety: failed to delete workspace",
            message=frappe.get_traceback(),
        )
