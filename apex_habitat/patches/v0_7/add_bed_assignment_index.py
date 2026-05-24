"""Add performance index on Accommodation Assignment.bed field.

MariaDB does not support partial (filtered) unique indexes, so true DB-level
uniqueness for active bed assignments is not achievable here.
Application-level enforcement is in accommodation_assignment.validate() +
on_submit() SELECT FOR UPDATE.

This patch adds a non-unique index on `bed` to speed up occupancy lookups.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Accommodation Assignment"):
        return

    # Add index on `bed` field if not already present
    try:
        frappe.db.sql(
            "ALTER TABLE `tabAccommodation Assignment` "
            "ADD INDEX IF NOT EXISTS `idx_asgn_bed` (`bed`(140))"
        )
    except Exception:
        # Index may already exist — ignore
        pass

    # Add composite index on (bed, docstatus, check_out_date) for occupancy queries
    try:
        frappe.db.sql(
            "ALTER TABLE `tabAccommodation Assignment` "
            "ADD INDEX IF NOT EXISTS `idx_asgn_bed_active` (`bed`(140), `docstatus`, `check_out_date`)"
        )
    except Exception:
        pass

    frappe.db.commit()
