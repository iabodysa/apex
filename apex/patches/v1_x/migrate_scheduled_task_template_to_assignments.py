# Copyright (c) 2026, AFMCO and contributors
"""ONE-TIME migration: create a Scheduled Task Assignment for every existing
Scheduled Task Template that had a `building` field set.

Background: the old design stored one building per template
(N×M templates). The new design uses a separate Scheduled Task Assignment DocType
(template → building). This patch reads the legacy `building` column directly from
the DB table and creates one Assignment per unique (template, building) pair.

ORDERING (critical): registered in the `[pre_model_sync]` section of patches.txt so
it runs BEFORE `sync_all()`. The same v2.0.0 change that ships this patch removes the
`building` field from the Scheduled Task Template DocType JSON, so `sync_all()` drops
the `building` column on this very migrate. Running pre-sync guarantees the column is
still present when the SELECT below reads it; in post_model_sync the column would
already be gone and the whole backfill would silently no-op (the try/except would
swallow "Unknown column 'building'").

Idempotency guards:
- Skips if an Assignment already exists for the same (template, building) pair.
- Skips templates whose building is NULL or empty.
- Safe to re-run; no-op on fresh installs (fresh installs mark patches as already
  run without executing them, and the legacy column never existed there anyway).

PRUNE from patches.txt once every deployed site has run it (check tabPatch Log).
"""

from __future__ import annotations

import frappe


def execute():
    # [#abyl1l]
    try:
        templates = frappe.db.sql(
            """SELECT name, building FROM `tabScheduled Task Template`
               WHERE building IS NOT NULL AND building != ''""",
            as_dict=True,
        )
    except Exception:
        # [#419o9y]
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
        # Row-scoped: a bare rollback discarded every assignment already migrated in
        # this run, and the `created` counter kept climbing, so the log reported rows
        # that no longer existed.
        frappe.db.savepoint("sta_row")
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
            frappe.db.rollback(save_point="sta_row")
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
