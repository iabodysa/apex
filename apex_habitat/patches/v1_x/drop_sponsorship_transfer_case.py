# ONE-TIME cleanup — safe to PRUNE once every deployed site has run it.
#
# Drops the out-of-scope "Sponsorship Transfer Case" DocType and its backing
# table. The kafala-transfer case (a Qiwa-status governance/HR process) was
# decided to be out of scope for the app's cost/operations core and removed
# wholesale: DocType, its native Workflow, permission hooks, number card and the
# Compliance workspace references are all gone from source. On an installed
# pre-production site the DocType record / table (holding only test data) may
# still linger, so this removes them. Its Workflow / Workflow State / Workflow
# Action Master masters are cleared automatically with the DocType (force=1).
#
# Idempotent: a no-op on a fresh install or once already dropped.

import frappe


def execute():
    has_doctype = frappe.db.exists("DocType", "Sponsorship Transfer Case")
    has_table = "tabSponsorship Transfer Case" in frappe.db.get_tables()

    if not (has_doctype or has_table):
        return  # fresh install or already dropped

    try:
        # Remove the native Workflow bound to the DocType first so its deletion
        # does not block on a Link to the doc type. Existence-guarded + idempotent.
        if frappe.db.exists("Workflow", "Sponsorship Transfer Case Workflow"):
            frappe.delete_doc(
                "Workflow",
                "Sponsorship Transfer Case Workflow",
                force=1,
                ignore_missing=True,
                ignore_permissions=True,  # audit-ok: system-managed schema cleanup patch
            )

        # force=1 drops the table too; ignore_missing keeps this idempotent.
        frappe.delete_doc(
            "DocType",
            "Sponsorship Transfer Case",
            force=1,
            ignore_missing=True,
            ignore_permissions=True,  # audit-ok: system-managed schema cleanup patch
        )
        # Drop a stray table left behind if the DocType record was already gone.
        if "tabSponsorship Transfer Case" in frappe.db.get_tables():
            frappe.db.sql_ddl("DROP TABLE IF EXISTS `tabSponsorship Transfer Case`")

        frappe.db.commit()
        frappe.logger().info(
            "apex_habitat patch: dropped out-of-scope DocType 'Sponsorship Transfer Case'"
        )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="drop_sponsorship_transfer_case: failed to drop DocType",
            message=frappe.get_traceback(),
        )
