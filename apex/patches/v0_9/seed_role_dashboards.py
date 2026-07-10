# Copyright (c) 2026, AFMCO and contributors
"""Seed the 4 new role-based dashboards. Idempotent."""

import frappe
from apex.apex_core.setup.seeders.habitat_dashboard_seed import seed_role_dashboards


def execute():
    try:
        seed_role_dashboards()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="seed_role_dashboards failed", message=frappe.get_traceback())
