# ONE-TIME cleanup — safe to PRUNE once every deployed site has run it.
#
# Drops the now-dead "Approval Request" DocType (and its backing table), plus the
# orphaned "Salis Authority Tier" child table. The custom Salis approval
# tier-engine (salis_lib: TIERS / ROLE_TIER / ensure_approval / escalation) was
# retired when the six approval DocTypes were migrated to native Frappe Workflow:
# segregation of duties now lives on the workflow transitions themselves
# (allow_self_approval=0 + maker != approver conditions), so nothing creates an
# Approval Request anymore and no controller calls ensure_approval. The Salis
# Authority Tier child table only fed the deleted role->tier map, so it goes too.
# Both held only pre-production test rows; they are discarded with the DocTypes
# (no migration of stored rows is performed).
#
# Idempotent: a no-op on a fresh install or once already dropped.

import frappe

_DOCTYPES = ("Approval Request", "Salis Authority Tier")


def execute():
    for doctype in _DOCTYPES:
        _drop(doctype)


def _drop(doctype):
    table = "tab" + doctype
    has_doctype = frappe.db.exists("DocType", doctype)
    has_table = table in frappe.db.get_tables()

    if not (has_doctype or has_table):
        return  # fresh install or already dropped

    try:
        # Remove any native Workflow bound to the DocType first so its deletion
        # does not block on a Link to the doc type. Existence-guarded + idempotent.
        workflow = doctype + " Workflow"
        if frappe.db.exists("Workflow", workflow):
            frappe.delete_doc(
                "Workflow",
                workflow,
                force=1,
                ignore_missing=True,
                ignore_permissions=True,  # audit-ok: system-managed schema cleanup patch
            )

        # force=1 drops the table too; ignore_missing keeps this idempotent.
        frappe.delete_doc(
            "DocType",
            doctype,
            force=1,
            ignore_missing=True,
            ignore_permissions=True,  # audit-ok: system-managed schema cleanup patch
        )
        # Drop a stray table left behind if the DocType record was already gone.
        if table in frappe.db.get_tables():
            frappe.db.sql_ddl("DROP TABLE IF EXISTS `{0}`".format(table))

        frappe.db.commit()
        frappe.logger().info(
            "apex_habitat patch: dropped obsolete DocType '{0}'".format(doctype)
        )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="drop_approval_request: failed to drop DocType '{0}'".format(doctype),
            message=frappe.get_traceback(),
        )
