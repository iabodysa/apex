# Copyright (c) 2026, afmcoltd

import frappe


def execute():
    if not frappe.db.table_exists("Scheduled Task Instance"):
        return
    if not frappe.db.sql(
        """SELECT 1 FROM information_schema.statistics
           WHERE table_schema = DATABASE()
             AND table_name = 'tabScheduled Task Instance'
             AND index_name = 'unique_sti_template_due_status'
           LIMIT 1"""
    ):
        return
    frappe.db.sql(
        "ALTER TABLE `tabScheduled Task Instance` DROP INDEX `unique_sti_template_due_status`"
    )
