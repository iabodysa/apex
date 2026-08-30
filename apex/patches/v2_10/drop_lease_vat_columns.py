# Copyright (c) 2026, afmcoltd

import frappe


COLUMNS = ("tax_rate", "tax_amount", "grand_total")


def execute():
    if not frappe.db.table_exists("Lease"):
        return
    present = set(frappe.db.get_table_columns("Lease")) & set(COLUMNS)
    if not present:
        return
    frappe.db.sql_ddl(
        "alter table `tabLease` "
        + ", ".join(f"drop column `{column}`" for column in sorted(present))
    )
