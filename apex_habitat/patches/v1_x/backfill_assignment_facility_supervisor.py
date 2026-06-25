"""ONE-TIME backfill: set Accommodation Assignment.responsible_facility_supervisor
from the row's building.responsible_facility_supervisor when it is still empty.

The field fetches from the building (fetch_from + fetch_if_empty) on save, so new
rows self-populate; rows saved before the field existed stay empty and the Expected
Checkout reminder never reaches the building supervisor for them. This copies the
building's supervisor into each empty assignment.

Idempotency guards:
- Only touches rows whose responsible_facility_supervisor is empty (never clobbers).
- Skips rows whose building has no supervisor set (legitimate — nothing to copy).
- Writes via frappe.db.set_value (update_modified=False) to avoid save/validation
  churn on historical rows.
- Safe to re-run and a no-op on fresh installs.

PRUNE from patches.txt once every deployed site has run it (check tabPatch Log).
"""

from __future__ import annotations

import frappe

_DOCTYPE = "Accommodation Assignment"


def execute():
    rows = frappe.get_all(
        _DOCTYPE,
        filters={
            "responsible_facility_supervisor": ["in", [None, ""]],
            "building": ["is", "set"],
        },
        fields=["name", "building"],
    )
    if not rows:
        return

    # Resolve each distinct building's supervisor once, not per assignment row.
    supervisor_by_building = {}
    updated = 0
    skipped = 0

    for row in rows:
        building = row.building
        if building not in supervisor_by_building:
            supervisor_by_building[building] = frappe.db.get_value(
                "Accommodation Building", building, "responsible_facility_supervisor"
            )
        supervisor = supervisor_by_building[building]
        if not supervisor:
            skipped += 1
            continue

        frappe.db.set_value(
            _DOCTYPE,
            row.name,
            "responsible_facility_supervisor",
            supervisor,
            update_modified=False,
        )
        updated += 1

    frappe.logger().info(
        f"backfill_assignment_facility_supervisor: updated={updated}, skipped={skipped}"
    )
