# Copyright (c) 2026, afmcoltd
import frappe

RENAMES = (
    ("Safety Task Catalog", "task_code", "STC-"),
    ("Custody Article", "article_name", "CUST-ART-"),
)


def execute():
    for doctype, keyfield, prefix in RENAMES:
        if not frappe.db.exists("DocType", doctype):
            continue
        rows = frappe.get_all(
            doctype,
            filters={"name": ["like", f"{prefix}%"]},
            fields=["name", keyfield],
        )
        for row in rows:
            target = (row.get(keyfield) or "").strip()
            if not target or target == row["name"]:
                continue
            if frappe.db.exists(doctype, target):
                frappe.throw(
                    frappe._("{0} {1} cannot take the name {2}, which is already used.").format(
                        doctype, row["name"], target
                    )
                )
            frappe.rename_doc(doctype, row["name"], target, force=True, show_alert=False)
        frappe.db.delete("Series", {"name": prefix})
