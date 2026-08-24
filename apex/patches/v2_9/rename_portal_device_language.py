# Copyright (c) 2026, afmcoltd

import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
    if not frappe.db.table_exists("Portal Device"):
        return
    columns = frappe.db.get_table_columns("Portal Device")
    if "language" not in columns:
        return
    if "chosen_language" in columns:
        frappe.db.sql_ddl("alter table `tabPortal Device` drop column `language`")
        return
    frappe.reload_doc("apex_core", "doctype", "portal_device")
    rename_field("Portal Device", "language", "chosen_language")
