# Copyright (c) 2026, AFMCO and contributors
"""V2.0.0 — B3 (P-157) dashboards/charts/number-cards cleanup (ONE-TIME).

The B3 wave deleted duplicate twins and renamed several Dashboard Charts, Number
Cards and Dashboards by shipping them under NEW is_standard=1 module JSON (new
folder + new `name`). Frappe's is_standard import is add/update-by-name only, so
the OLD-named rows left in the DB on an upgrading site are never removed by
migrate and would linger as orphans (a stale twin, or the pre-rename copy shadowing
its renamed successor in the Number Card / Dashboard Chart list). This run-once
patch force-deletes those old rows by exact name.

GUARD: each row is deleted only if it still exists; force + ignore_permissions so a
referenced chart/card is removed regardless of link checks (the shipped dashboards
already point at the canonical/renamed names). Idempotent: re-running finds nothing.
No-op on fresh installs (the old names were never created). PRUNE once every deployed
site has run it (tracked in tabPatch Log).
"""

import frappe

# Twins deleted outright (canonical kept) + pre-rename copies now shipped under new names.
LEGACY_CHARTS = [
    # deleted twins
    "Leases by Status",
    "Movement Trips by Status",
    "Fuel Spend by Platform",
    "Fuel Spend Trend",
    # clarity renames (old names)
    "Vehicle Utilisation",
    "Ledger Cost by Type",
    "Monthly Cost Bleeding",
    "Cost Bleed by Building",
]

LEGACY_CARDS = [
    # deleted twins
    "Vacant Beds",
    "Fuel Spend This Month",
    "Salis Compliance Drivers Active Drivers",
    # clarity renames (old names)
    "Compliance Percent",
    "Buildings Over Threshold",
    "Pending on Manifest",
    "Ledger Cost This Month",
    # broken raw-prefixed docnames (old names)
    "salis_fuel Approved This Month",
    "salis_fuel Litres Dispensed This Month",
    "salis_fuel Open Claim Disputes",
    "salis_workers_transport Passenger Manifests Today",
    "salis_workers_transport Scheduled Awaiting Dispatch",
    "salis_workers_transport Trips Dispatched Today",
]

LEGACY_DASHBOARDS = [
    "Salis - Representatives Fleet",
    "Salis - Workers Transport",
]


def execute():
    for doctype, names in (
        ("Dashboard Chart", LEGACY_CHARTS),
        ("Number Card", LEGACY_CARDS),
        ("Dashboard", LEGACY_DASHBOARDS),
    ):
        for name in names:
            if frappe.db.exists(doctype, name):
                frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)  # audit-ok
    frappe.db.commit()
