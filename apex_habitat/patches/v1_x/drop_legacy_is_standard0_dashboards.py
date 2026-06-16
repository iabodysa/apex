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

# [#9o3tww]
LEGACY_DASHBOARDS = [
    # [#h55sfk]
    "Habitat Dashboard",
    "Accommodation Manager Dashboard",
    "Resident Supervisor Dashboard",
    "Finance Manager Dashboard",
    "Internal Auditor Dashboard",
    # [#eavzps]
    "Fleet Manager Dashboard",
    "Fleet Supervisor Dashboard",
    "Salis Finance Manager Dashboard",  # [#ak5kq1]
    "Salis - Workers Transport",
    "Salis - Representatives Fleet",
    # [#nkctau]
    "Movement Operations Dashboard",  # [#ak5kq1]
]


def execute():
    for name in LEGACY_DASHBOARDS:
        # [#mxgrde]
        # [#5v465w]
        if frappe.db.get_value("Dashboard", name, "is_standard") == 0:
            frappe.delete_doc("Dashboard", name, force=True, ignore_permissions=True)
    frappe.db.commit()
