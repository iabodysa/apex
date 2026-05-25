"""Seed the operational Assignment Rules (Maintenance/Resident intake) on existing
sites, disabled with an Administrator placeholder. Idempotent.
"""

import frappe

from apex_habitat.habitat.assignment_rules_seed import seed_assignment_rules


def execute():
    try:
        seed_assignment_rules()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_assignment_rules failed",
            message=frappe.get_traceback(),
        )
