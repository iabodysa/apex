# Copyright (c) 2026, afmcoltd
"""Drop the storage the retired Salary Deduction DocTypes left behind.

``apex.patches.v2_6.converge_native_support_and_recovery`` deleted the two DocType
records and migrated their values onto the native Employee Advance recovery path, but
``frappe.delete_doc("DocType", ...)`` removes only the metadata row
(``frappe/model/delete_doc.py:207-227``; ``frappe/model/sync.py:149
remove_orphan_doctypes`` documents this as deliberate): the child table
``Salary Deduction Type Rule`` owned and the ``tabSingles`` rows ``Salary Deduction
Policy`` owned are left standing. That patch already ran and Frappe never replays a
patch by name, so the remaining storage is dropped here.
"""

import frappe


def execute():
    """Drop the orphaned child table and purge the orphaned Singles rows."""
    if frappe.db.table_exists("Salary Deduction Type Rule"):
        frappe.db.sql_ddl("drop table if exists `tabSalary Deduction Type Rule`")
    frappe.db.delete("Singles", {"doctype": "Salary Deduction Policy"})
