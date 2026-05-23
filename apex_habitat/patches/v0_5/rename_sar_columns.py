"""Dev patch: remove _sar suffix from 3 Currency fieldnames.

Chain after v0_4 patch which renamed monthly_rent_sar → rent_amount_sar.
This patch renames rent_amount_sar → rent_amount, total_scheduled_sar → total_scheduled
on tabAccommodation Lease, and amount_sar → amount on tabRent Payment Schedule.
"""
import frappe


def execute():
    _rename("tabAccommodation Lease", "rent_amount_sar", "rent_amount",
            "decimal(21,9) NOT NULL DEFAULT 0")
    _rename("tabAccommodation Lease", "total_scheduled_sar", "total_scheduled",
            "decimal(21,9) NOT NULL DEFAULT 0")
    _rename("tabRent Payment Schedule", "amount_sar", "amount",
            "decimal(21,9) NOT NULL DEFAULT 0")
    frappe.clear_cache()


def _rename(table, old_col, new_col, col_def):
    exists = frappe.db.sql(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "  AND TABLE_NAME = %s "
        "  AND COLUMN_NAME = %s",
        (table, old_col),
    )
    if not exists:
        return
    frappe.db.sql(
        f"ALTER TABLE `{table}` CHANGE `{old_col}` `{new_col}` {col_def}"
    )
    frappe.logger().info(f"apex_habitat patch: renamed {table}.{old_col} → {new_col}")
