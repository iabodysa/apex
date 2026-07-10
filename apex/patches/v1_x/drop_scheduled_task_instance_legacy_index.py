# Copyright (c) 2026, AFMCO and contributors
"""Drop the legacy unique_sti_template_due_status index from Scheduled Task Instance.

Background (T-552 Phase B): the old UNIQUE(template, due_date, docstatus) index was
designed for the one-template-per-building generator. Phase B allows multiple
Scheduled Task Assignments per template, so two assignments for the same template
would collide on this index. The new idempotency guard is the Phase B index
UNIQUE(assignment, task_catalog, due_date, docstatus).
"""

import frappe


def execute():
    try:
        frappe.db.sql(
            "ALTER TABLE `tabScheduled Task Instance` DROP INDEX `unique_sti_template_due_status`"
        )
        frappe.logger().info(
            "drop_scheduled_task_instance_legacy_index: index unique_sti_template_due_status dropped."
        )
    except Exception:
        frappe.logger().info(
            "drop_scheduled_task_instance_legacy_index: index already absent — no-op."
        )
