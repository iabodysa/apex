# Copyright (c) 2026, afmcoltd

import frappe


def execute():
    if not frappe.db.exists("DocType", "Driver Attendance Image"):
        _drop_orphan_table()
        return

    rows = frappe.get_all(
        "Driver Attendance Image",
        fields=["name", "parent", "image"],
        filters={"parenttype": "Driver Attendance", "image": ["is", "set"]},
    )
    for row in rows:
        already = frappe.db.exists(
            "File",
            {
                "attached_to_doctype": "Driver Attendance",
                "attached_to_name": row.parent,
                "file_url": row.image,
            },
        )
        if already:
            continue
        frappe.get_doc(
            {
                "doctype": "File",
                "file_url": row.image,
                "attached_to_doctype": "Driver Attendance",
                "attached_to_name": row.parent,
            }
        ).insert()

    frappe.delete_doc("DocType", "Driver Attendance Image", force=True)
    _drop_orphan_table()


def _drop_orphan_table():
    if frappe.db.table_exists("Driver Attendance Image"):
        frappe.db.sql_ddl("drop table if exists `tabDriver Attendance Image`")
