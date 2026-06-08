"""Drop the legacy is_standard=0 Dashboard rows so migrate re-imports them as
is_standard=1 from the new native module JSON.

The Habitat + Salis Dashboards used to be hand-built at runtime by three seeders
as is_standard=0 records. They now ship as native is_standard=1 module JSON under
``<module>/<module>_dashboard/<slug>/<slug>.json`` (imported by Frappe's
``sync_dashboards()`` on install + migrate — like ERPNext).

Frappe's dashboard import (``import_file_by_path``) skips re-importing a record
whose stored content matches, and an existing is_standard=0 row would otherwise
shadow the shipped is_standard=1 definition. This patch removes the stale
is_standard=0 rows by name so the post_model_sync ``sync_dashboards`` step recreates
them from the JSON with is_standard=1.

GUARD: a Dashboard is deleted ONLY if it currently exists AND its is_standard == 0.
A row already promoted to is_standard=1 (e.g. re-imported on an earlier migrate),
or any admin-created Dashboard, is left untouched. Idempotent: re-running finds
nothing to delete.

Two of the listed names (``Salis Finance Manager Dashboard``,
``Movement Operations Dashboard``) are NOT shipped as JSON — every chart/card they
referenced was a runtime-only spec, so after filtering to on-disk is_standard=1
records they have 0 charts and a Dashboard's charts table is mandatory. Their
stale is_standard=0 rows are simply removed (not re-imported).
"""

import frappe

# Every Dashboard name the three retired seeders created as is_standard=0.
LEGACY_DASHBOARDS = [
    # habitat_dashboard_seed.py
    "Habitat Dashboard",
    "Accommodation Manager Dashboard",
    "Resident Supervisor Dashboard",
    "Finance Manager Dashboard",
    "Internal Auditor Dashboard",
    # salis_dashboard_seed.py
    "Fleet Manager Dashboard",
    "Fleet Supervisor Dashboard",
    "Salis Finance Manager Dashboard",  # not re-shipped (0 standard charts)
    "Salis - Workers Transport",
    "Salis - Representatives Fleet",
    # salis_movement_dashboard_seed.py
    "Movement Operations Dashboard",  # not re-shipped (0 standard charts)
]


def execute():
    for name in LEGACY_DASHBOARDS:
        # Guard: only delete a stale runtime-built (is_standard=0) row. Never touch a
        # row already promoted to is_standard=1 or an admin-created Dashboard.
        if frappe.db.get_value("Dashboard", name, "is_standard") == 0:
            frappe.delete_doc("Dashboard", name, force=True, ignore_permissions=True)
    frappe.db.commit()
