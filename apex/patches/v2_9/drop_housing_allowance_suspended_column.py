# Copyright (c) 2026, afmcoltd
"""Drop the storage the retired housing-allowance suspension flag left behind.

``housing_allowance_suspended`` was a read-only Check on Housing Assignment written
only by the Salary Deduction Policy path that
``apex.patches.v2_6.converge_native_support_and_recovery`` retired. Nothing in the tree
has written it since, so the operator saw a flag that could never turn on, and the field
is gone from the DocType.

Removing a field from a DocType does not remove its column: ``db_manager`` only adds and
alters columns during a sync, and Frappe leaves an unused one standing rather than
risking data (``frappe/database/schema.py``). The column is dropped here so the row does
not carry a value no screen can show and no code can read.
"""

import frappe


COLUMN = "housing_allowance_suspended"


def execute():
    """Drop the orphaned column if this site still carries it."""
    if COLUMN in frappe.db.get_table_columns("Housing Assignment"):
        frappe.db.sql_ddl(f"alter table `tabHousing Assignment` drop column `{COLUMN}`")
