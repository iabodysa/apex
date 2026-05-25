"""Seed the Room Readiness Kanban board on existing sites. Idempotent; the seed
skips the Resident/Maintenance boards already present and creates only the new one.
"""

import frappe

from apex_habitat.habitat.kanban_seed import seed_kanban_boards


def execute():
    try:
        seed_kanban_boards()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_room_readiness_kanban failed",
            message=frappe.get_traceback(),
        )
