# ONE-TIME cleanup — safe to PRUNE once every deployed site has run it.
#
# Drops the obsolete custom "Support Ticket" DocType (and its child "Ticket
# Message") plus the "Support Ticket Workflow", which were replaced by the
# native ERPNext "Issue" DocType + Service Level Agreement. The driver portal
# now raises an Issue, and the desk uses Issue's native status flow and SLA, so
# the hand-rolled DocTypes and their backing tables have no remaining reader and
# are discarded (no data migration is performed — pre-production / test data).
#
# Order matters: the Workflow is removed first (it Links to Support Ticket as its
# document_type), then the parent DocType, then the child table DocType. Each
# delete is force=1 (drops the table) + ignore_missing=1 (idempotent), with a
# DROP TABLE fallback for a stray table left behind if the DocType record was
# already gone.
#
# Idempotent: a no-op on a fresh install or once already dropped.

import frappe

_TABLES = ["tabSupport Ticket", "tabTicket Message"]


def execute():
    has_workflow = frappe.db.exists("Workflow", "Support Ticket Workflow")
    has_parent = frappe.db.exists("DocType", "Support Ticket")
    has_child = frappe.db.exists("DocType", "Ticket Message")
    site_tables = set(frappe.db.get_tables())
    has_table = any(t in site_tables for t in _TABLES)

    if not (has_workflow or has_parent or has_child or has_table):
        return  # fresh install or already dropped

    try:
        # 1) Workflow first — it Links to Support Ticket as its document_type.
        if has_workflow:
            frappe.delete_doc(
                "Workflow",
                "Support Ticket Workflow",
                force=1,
                ignore_missing=True,
                ignore_permissions=True,  # audit-ok: system-managed schema cleanup patch
            )

        # 2) Parent DocType (force drops the table; ignore_missing keeps it idempotent).
        frappe.delete_doc(
            "DocType",
            "Support Ticket",
            force=1,
            ignore_missing=True,
            ignore_permissions=True,  # audit-ok: system-managed schema cleanup patch
        )

        # 3) Child table DocType.
        frappe.delete_doc(
            "DocType",
            "Ticket Message",
            force=1,
            ignore_missing=True,
            ignore_permissions=True,  # audit-ok: system-managed schema cleanup patch
        )

        # 4) Drop any stray tables left behind if the DocType record was already gone.
        current_tables = set(frappe.db.get_tables())
        for table in _TABLES:
            if table in current_tables:
                frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table}`")

        frappe.db.commit()
        frappe.logger().info(
            "apex_habitat patch: dropped obsolete 'Support Ticket' / 'Ticket Message' "
            "DocTypes and 'Support Ticket Workflow' (replaced by native Issue + SLA)"
        )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="drop_support_ticket: failed to drop DocTypes",
            message=frappe.get_traceback(),
        )
