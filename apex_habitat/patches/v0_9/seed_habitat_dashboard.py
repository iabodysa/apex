"""Seed the Habitat Dashboard on existing sites. Idempotent."""

import frappe

from apex_habitat.habitat.dashboard_seed import seed_habitat_dashboard


def execute():
    try:
        seed_habitat_dashboard()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="seed_habitat_dashboard failed", message=frappe.get_traceback())
