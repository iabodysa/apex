"""Seed the Salis operational native-paradigm artifacts: Notifications, Kanban
Boards, and Assignment Rules.

Mirrors the Habitat pattern (``patches/v0_8/seed_*`` -> module seeds): the seed
logic lives in the idempotent, existence-guarded ``salis/*_seed.py`` modules
(single source of truth). This patch — and the app's ``after_install`` /
``after_migrate`` hooks — reuse those same functions, so a fresh install gets
the artifacts immediately while already-installed sites pick them up on migrate.

PERMANENT (keep, do NOT prune): each function seeds DISTINCT records and fresh
installs must replay it. All are idempotent (also called from the hooks), not
redundant. Each step is independently wrapped so a partially installed module
never aborts the migrate or the surrounding Habitat/Salis seeds.
"""

import frappe

from apex_habitat.salis.notifications_seed import seed_salis_notifications
from apex_habitat.salis.kanban_seed import seed_salis_kanban_boards
from apex_habitat.salis.assignment_rules_seed import seed_salis_assignment_rules


def execute():
    for step in (
        seed_salis_notifications,
        seed_salis_kanban_boards,
        seed_salis_assignment_rules,
    ):
        try:
            step()
        except Exception:
            # A seed must NEVER crash install/migrate — log and continue.
            frappe.db.rollback()
            frappe.log_error(
                title=f"seed_salis_operations_artifacts failed: {step.__name__}",
                message=frappe.get_traceback(),
            )
