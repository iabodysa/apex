# Copyright (c) 2026, afmcoltd

import re

import frappe
from frappe.desk.notifications import clear_doctype_notifications

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def cleanup_orphaned_workflow_actions():
    for wf in frappe.get_all("Workflow", fields=["document_type", "workflow_state_field"]):
        dt, sf = wf.document_type, wf.workflow_state_field
        if not (dt and sf) or not _IDENT.match(sf) or not frappe.db.table_exists(dt):
            continue
        try:
            frappe.db.sql(
                f"""DELETE wa FROM `tabWorkflow Action` wa
                    INNER JOIN `tab{dt}` doc ON doc.name = wa.reference_name
                    WHERE wa.status = 'Open' AND wa.reference_doctype = %(dt)s
                      AND doc.`{sf}` IS NOT NULL AND doc.`{sf}` != wa.workflow_state""",
                {"dt": dt},
            )
            WA = frappe.qb.DocType("Workflow Action")
            DocTbl = frappe.qb.DocType(dt)
            (
                frappe.qb.from_(WA)
                .delete()
                .where(WA.status == "Open")
                .where(WA.reference_doctype == dt)
                .where(WA.reference_name.notin(frappe.qb.from_(DocTbl).select(DocTbl.name)))
            ).run()
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"cleanup_orphaned_workflow_actions: {dt}")

    open_doctypes = frappe.get_all(
        "Workflow Action", filters={"status": "Open"}, pluck="reference_doctype", distinct=True
    )
    for dt in open_doctypes:
        if not dt or (frappe.db.exists("DocType", dt) and frappe.db.table_exists(dt)):
            continue
        try:
            frappe.db.delete("Workflow Action", {"status": "Open", "reference_doctype": dt})
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"cleanup_orphaned_workflow_actions (missing DocType): {dt}")

    clear_doctype_notifications("Workflow Action")
