"""Seed the operational Kanban Boards (Resident Requests, Maintenance Requests) on
existing sites. Idempotent; boards are public and admins may edit them afterwards.
"""

import frappe

from apex_habitat.habitat.kanban_seed import seed_kanban_boards


def execute():
    try:
        seed_kanban_boards()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_kanban_boards failed",
            message=frappe.get_traceback(),
        )
