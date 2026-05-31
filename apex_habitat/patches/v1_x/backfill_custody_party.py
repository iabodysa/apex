import frappe

# Back-fill party_type / party on the TIER-2 custody doctypes from their legacy
# Employee links (Batch 3 of the arrival redesign). Each custody doctype names its
# Employee link differently, so the column is parameterised per doctype.
#
# [AHX-FRP-0003] Runs POST model sync (listed under [post_model_sync] in
# patches.txt) so the party_type / party columns already exist. Same idempotent,
# existence-guarded pattern as patches/v1_x/backfill_worker_party.
#
# Idempotent: only touches rows whose `party` is still empty, so a re-run (or a
# fresh install with no such rows) is a no-op. Existence-guarded on both the table
# and the columns, so it can never raise a schema error during migrate.

CUSTODY_PARTY = {
    "Custody Issue": "issued_to_employee",
    "Custody Return": "returned_by_employee",
    "Custody Damage Assessment": "employee",
}


def execute():
    for doctype, emp_field in CUSTODY_PARTY.items():
        if not frappe.db.table_exists(doctype):
            continue
        columns = set(frappe.db.get_table_columns(doctype))
        if not {"party_type", "party", emp_field} <= columns:
            # Schema not yet synced for this doctype; nothing to backfill safely.
            continue
        frappe.db.sql(
            f"""
            UPDATE `tab{doctype}`
            SET party_type = 'Employee', party = `{emp_field}`
            WHERE (party IS NULL OR party = '')
              AND `{emp_field}` IS NOT NULL AND `{emp_field}` != ''
            """
        )
