# Copyright (c) 2026, AFMCO and contributors
"""ONE-TIME migration: create a Scheduled Task Assignment for every existing
Scheduled Task Template that had a `building` field set.

Background (T-552 Phase B): the old design stored one building per template
(N×M templates). The new design uses a separate Scheduled Task Assignment DocType
(template → building). This patch reads the legacy `building` column directly from
the DB table (the column still exists in the database even after the field is removed
from the DocType JSON — until migrate drops it) and creates one Assignment per unique
(template, building) pair.

Idempotency guards:
- Skips if an Assignment already exists for the same (template, building) pair.
- Skips templates whose building is NULL or empty.
- Safe to re-run; no-op on fresh installs.

PRUNE from patches.txt once every deployed site has run it (check tabPatch Log).
"""

from __future__ import annotations

import frappe


def execute():
    # Read the legacy building column directly from the DB; it persists until
    # bench migrate actually runs ALTER TABLE to drop it.
    try:
        templates = frappe.db.sql(
            """SELECT name, building FROM `tabScheduled Task Template`
               WHERE building IS NOT NULL AND building != ''""",
            as_dict=True,
        )
    except Exception:
        # The column may already have been dropped on a fresh install that
        # never had the building field — this is a no-op in that case.
        frappe.logger().info(
            "migrate_scheduled_task_template_to_assignments: "
            "building column not found — nothing to migrate."
        )
        return

    created = 0
    for t in templates:
        if frappe.db.exists(
            "Scheduled Task Assignment",
            {"template": t.name, "building": t.building},
        ):
            continue
        try:
            frappe.get_doc({
                "doctype": "Scheduled Task Assignment",
                "template": t.name,
                "building": t.building,
                "effective_from": frappe.utils.today(),
                "is_active": 1,
            }).insert(ignore_permissions=True)
            created += 1
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                message=frappe.get_traceback(),
                title=(
                    f"migrate_scheduled_task_template_to_assignments: "
                    f"insert failed for template={t.name}"
                )[:140],
            )

    frappe.db.commit()
    frappe.logger().info(
        f"migrate_scheduled_task_template_to_assignments: created {created} assignment(s)."
    )
    return created
