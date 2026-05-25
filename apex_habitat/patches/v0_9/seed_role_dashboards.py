"""Seed the 4 new role-based dashboards. Idempotent."""

import frappe
from apex_habitat.habitat.dashboard_seed import seed_role_dashboards


def execute():
    try:
        seed_role_dashboards()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="seed_role_dashboards failed", message=frappe.get_traceback())
