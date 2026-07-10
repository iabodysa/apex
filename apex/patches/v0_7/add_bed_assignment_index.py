# Copyright (c) 2026, AFMCO and contributors
"""Add performance index on Accommodation Assignment.bed field.

MariaDB does not support partial (filtered) unique indexes, so true DB-level
uniqueness for active bed assignments is not achievable here.
Application-level enforcement is in accommodation_assignment.validate() +
on_submit() SELECT FOR UPDATE.

This patch adds a non-unique index on `bed` to speed up occupancy lookups.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Housing Assignment"):
        return

    # [#44ssmk]
    try:
        frappe.db.sql(
            "ALTER TABLE `tabHousing Assignment` "
            "ADD INDEX IF NOT EXISTS `idx_asgn_bed` (`bed`(140))"
        )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Patch: add idx_asgn_bed failed",
        )
        raise

    # [#cfszw1]
    try:
        frappe.db.sql(
            "ALTER TABLE `tabHousing Assignment` "
            "ADD INDEX IF NOT EXISTS `idx_asgn_bed_active` (`bed`(140), `docstatus`, `check_out_date`)"
        )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Patch: add idx_asgn_bed_active failed",
        )
        raise

    frappe.db.commit()
