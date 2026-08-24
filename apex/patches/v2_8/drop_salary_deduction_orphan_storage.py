# Copyright (c) 2026, afmcoltd

import frappe


def execute():
    if frappe.db.table_exists("Salary Deduction Type Rule"):
        frappe.db.sql_ddl("drop table if exists `tabSalary Deduction Type Rule`")
    frappe.db.delete("Singles", {"doctype": "Salary Deduction Policy"})
