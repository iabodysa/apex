"""Workflow housekeeping — orphaned Workflow Action cleanup (app-wide).

Frappe creates a Workflow Action per permitted approver when a document enters a
workflow state, and flips it to Completed when the document transitions. But an Open
row can be ORPHANED with no native cleanup: the document's state was advanced by a
direct DB write / data import / a deactivated workflow (Case B), or the document was
hard-deleted bypassing on_trash (Case A). Either way the stale Open row pollutes
every permitted user's Action Inbox forever. This daily job deletes ONLY those
orphaned OPEN rows — Completed rows are the audit trail and are never touched.

Wired into hooks.py scheduler_events["daily"]. Idempotent: a clean site is a no-op.
DELETE (not mark-Completed) is deliberate: is_workflow_action_already_created has no
status filter, so a Completed row would block re-creating an Open one if a cyclic
workflow ever re-entered the state.
"""

import re

import frappe
from frappe.desk.notifications import clear_doctype_notifications

# workflow_state_field is a DocType fieldname; validate it before interpolating it as
# a SQL column identifier (defence in depth — it comes from the Workflow master).
_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def cleanup_orphaned_workflow_actions():
    """Delete Open Workflow Actions whose document moved past the recorded state
    (Case B) or no longer exists (Case A). Per-workflow, guarded and isolated so one
    bad doctype never aborts the run."""
    for wf in frappe.get_all(
        "Workflow", filters={"is_active": 1}, fields=["document_type", "workflow_state_field"]
    ):
        dt, sf = wf.document_type, wf.workflow_state_field
        if not (dt and sf) or not _IDENT.match(sf) or not frappe.db.table_exists(dt):
            continue
        try:
            # Case B — the document has moved past the action's recorded state.
            # IS NOT NULL skips a document mid-save (transient null state).
            frappe.db.sql(
                f"""DELETE wa FROM `tabWorkflow Action` wa
                    INNER JOIN `tab{dt}` doc ON doc.name = wa.reference_name
                    WHERE wa.status = 'Open' AND wa.reference_doctype = %(dt)s
                      AND doc.`{sf}` IS NOT NULL AND doc.`{sf}` != wa.workflow_state""",
                {"dt": dt},
            )
            # Case A — the referenced document was hard-deleted (bypassed on_trash).
            frappe.db.sql(
                f"""DELETE FROM `tabWorkflow Action`
                    WHERE status = 'Open' AND reference_doctype = %(dt)s
                      AND reference_name NOT IN (SELECT name FROM `tab{dt}`)""",
                {"dt": dt},
            )
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"cleanup_orphaned_workflow_actions: {dt}")

    # Refresh the notification badge (accepts a doctype name; a no-op if unconfigured).
    clear_doctype_notifications("Workflow Action")
