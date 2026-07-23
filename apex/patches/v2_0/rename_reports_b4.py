"""V2-B4 (P-158): rename 8 Reports + drop 2 merged-into twins.

pre_model_sync — MUST run before the is_standard Report JSON re-import, else migrate
imports each new-named report as a fresh row and the old-named DB row orphans (and a
later old->new rename_doc would then collide with the freshly-imported new row).
rename_doc(force=True) carries the DB row (+ any Auto Email Report / links) onto the
new name; the on-disk JSON (already carrying the new name) is then re-imported cleanly.

Two twins were MERGED, not renamed, so their DB rows are deleted (their JSON is gone;
migrate is import-only and never removes an orphaned is_standard row):
  Fuel Claim vs Consumption -> folded into Fleet Payment Register
  Rental Variance Report    -> variance chart ported into Rental Settlement Register

Idempotent: skips a pair already renamed or absent; skips a twin already gone.
"""

import frappe

# [#p7abqf]
RENAMES = [
    ("Housing Supervisor Report", "Building Operations Summary"),
    ("Idle Resident Candidates", "Idle Resident Detection"),
    ("Maintenance Backlog", "Open Maintenance Requests"),
    ("Safety Round Compliance", "Safety Task Compliance Summary"),
    ("Scheduled Task Compliance", "Safety Task Execution Log"),
    ("Utility Variance Report", "Utility Variance"),
    ("Salis Payment Register", "Fleet Payment Register"),
    ("Salis Fleet Register", "Fleet Register"),
]

# [#gqbwcy]
MERGED_TWINS = [
    "Fuel Claim vs Consumption",
    "Rental Variance Report",
]


def execute():
    for old, new in RENAMES:
        if frappe.db.exists("Report", new):
            continue  # [#45ot3n]
        if not frappe.db.exists("Report", old):
            continue  # [#28qx78]
        frappe.rename_doc("Report", old, new, force=True)
        frappe.db.commit()

    for twin in MERGED_TWINS:
        if not frappe.db.exists("Report", twin):
            continue  # [#5tm6as]
        frappe.delete_doc("Report", twin, force=True, ignore_permissions=True)
        frappe.db.commit()
