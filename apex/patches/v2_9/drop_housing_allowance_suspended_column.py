# Copyright (c) 2026, afmcoltd

import frappe


COLUMN = "housing_allowance_suspended"


def execute():
    if COLUMN in frappe.db.get_table_columns("Housing Assignment"):
        frappe.db.sql_ddl(f"alter table `tabHousing Assignment` drop column `{COLUMN}`")
