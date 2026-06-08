"""RETIRED — Movement dashboard provisioning moved to native is_standard=1 JSON.

This seeder previously hand-built one ``Movement Operations Dashboard`` at runtime
as an is_standard=0 record, and (like ``salis_dashboard_seed.py``) re-created its
Dashboard Charts and Number Cards via ``_upsert_chart`` / ``_upsert_card``. The
deep audit flagged both the native-first violation and the double-provisioning,
so all record-building logic is removed.

The Movement dashboard is intentionally NOT shipped as JSON. Every chart it
referenced (Movement Trips by Status, Trip Fulfilment Over Time, Fuel Consumption
by Month, Rental Accrual by Office, Vehicle Utilisation, Cost Recovery by Type)
was a runtime-only spec built against background-engine DocTypes (Trip Fulfilment
Ledger, Fuel Consumption Ledger, Rental Accrual Ledger, Vehicle Utilisation
Snapshot, Movement Cost Recovery) — none of those charts ship as is_standard JSON
on disk. After filtering to on-disk is_standard=1 records the dashboard has 0
charts, and Dashboard.charts is a mandatory table, so it cannot be imported as a
standard record. When those engine charts/cards are later shipped as is_standard
JSON, add ``salis/salis_dashboard/movement_operations_dashboard/...json`` then.

The public entrypoint below is kept as a NO-OP stub because hooks.py historically
wired it into after_sync/after_migrate. A run-once patch
(``patches/v1_x/drop_legacy_is_standard0_dashboards``) deletes the old
is_standard=0 ``Movement Operations Dashboard`` row on upgrading sites.

Movement charts/cards that DO ship as is_standard JSON (e.g. Dispatch Trips by
Status, Open Fuel Exception Cases, Rental Accrual This Month, Blocked Driver
Clearances) are already surfaced on the shipped Salis dashboards.
"""


def seed_movement_dashboards(*args, **kwargs):
    """No-op after_sync/after_migrate entrypoint (retired — see module docstring)."""
