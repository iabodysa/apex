# ONE-TIME cleanup — safe to PRUNE once every deployed site has run it.
#
# Drops the obsolete "Salis Activity Log" DocType and its backing table. The
# custom activity log was ~90% redundant with native Frappe: create / submit /
# cancel / field changes on the Salis DocTypes are already captured by Version
# (track_changes is enabled on them) plus the automatic timeline comments, and
# genuine cross-document notes were moved onto the target document's timeline via
# add_comment. The stored rows had no reader, so they are discarded with the
# DocType (no migration to Comment is performed).
#
# Idempotent: a no-op on a fresh install or once already dropped.

import frappe


def execute():
    has_doctype = frappe.db.exists("DocType", "Salis Activity Log")
    has_table = "tabSalis Activity Log" in frappe.db.get_tables()

    if not (has_doctype or has_table):
        return  # fresh install or already dropped

    try:
        # force=1 drops the table too; ignore_missing keeps this idempotent.
        frappe.delete_doc(
            "DocType",
            "Salis Activity Log",
            force=1,
            ignore_missing=True,
            ignore_permissions=True,  # audit-ok: system-managed schema cleanup patch
        )
        # Drop a stray table left behind if the DocType record was already gone.
        if "tabSalis Activity Log" in frappe.db.get_tables():
            frappe.db.sql_ddl("DROP TABLE IF EXISTS `tabSalis Activity Log`")

        frappe.db.commit()
        frappe.logger().info(
            "apex_habitat patch: dropped obsolete DocType 'Salis Activity Log'"
        )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="drop_salis_activity_log: failed to drop DocType",
            message=frappe.get_traceback(),
        )
