import frappe

# Back-fill party_type / party on the worker-identity doctypes from the legacy
# `employee` Link (Batch 2 of the arrival redesign).
#
# Context: these seven doctypes gained a native party_type (Employee | Temporary
# Worker) + party Dynamic Link, with `employee` kept as a read-only compatibility
# mirror. Existing rows predate the party fields, so this one-time pass stamps
# party_type = 'Employee' and party = <employee> on every row that already has an
# employee but no party yet.
#
# [AHX-FRP-0003] Runs POST model sync (listed under [post_model_sync] in
# patches.txt) so the party_type / party columns already exist when the UPDATE
# runs. A backfill that needs columns added in the same release must never run
# pre-model-sync, or it would no-op against a not-yet-created column and never
# replay.
#
# Idempotent: only touches rows whose `party` is still empty, so a re-run (or a
# fresh install with no such rows) is a no-op. Existence-guarded on both the table
# and the three columns, so it can never raise a schema error during migrate.

PARTY_DOCTYPES = [
    "Accommodation Assignment",
    "Accommodation Checkout",
    "Room Bed Transfer",
    "Accommodation Resident Request",
    "Idle Resident Report",
    "Accommodation Ledger",
    "Masar Worker Token",
]


def execute():
    for doctype in PARTY_DOCTYPES:
        if not frappe.db.table_exists(doctype):
            continue
        columns = set(frappe.db.get_table_columns(doctype))
        if not {"party_type", "party", "employee"} <= columns:
            # Schema not yet synced for this doctype; nothing to backfill safely.
            continue
        frappe.db.sql(
            f"""
            UPDATE `tab{doctype}`
            SET party_type = 'Employee', party = employee
            WHERE (party IS NULL OR party = '')
              AND employee IS NOT NULL AND employee != ''
            """
        )
