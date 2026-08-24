# Copyright (c) 2026, afmcoltd
"""Remove the Driver Attendance Image child table and the field that held it.

Attendance photographs are attachments, and every DocType already accepts attachments
through the File DocType with no field of its own. The child table duplicated two of
File's columns and added a third, ``caption``, that nothing ever wrote — no controller,
no client script and no portal call reads or fills the table, so its removal moves no
data.

Rows are carried to File rather than dropped, because "nothing writes it" is a statement
about this tree and not about a site where somebody typed into the grid by hand. A row
with no ``image`` has nothing to carry and is left behind with the table.

Deleting the JSON alone would leave the DocType record and its table behind on every
site that already migrated, so the removal has to run here.
"""

import frappe


def execute():
    """Carry any stored image to a File attachment, then drop the child DocType.

    The two halves are guarded SEPARATELY on purpose. Deleting the DocType leaves its
    table standing, so a single early return on the DocType record would skip the DDL on
    exactly the site where the first half already ran.
    """
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
    """Drop the child table the DocType deletion leaves behind.

    Measured, not assumed: after ``delete_doc`` removes the DocType record and the
    parent's field, ``frappe.db.table_exists`` still answers True. An orphan table is
    the half-removal this patch exists to avoid.
    """
    if frappe.db.table_exists("Driver Attendance Image"):
        frappe.db.sql_ddl("drop table if exists `tabDriver Attendance Image`")
