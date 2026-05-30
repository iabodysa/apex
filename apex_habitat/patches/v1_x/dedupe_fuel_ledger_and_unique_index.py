import frappe

# Make the Fuel Consumption Ledger's DB-level UNIQUE backstop installable on an
# EXISTING site, even one that already accumulated duplicate accrual rows before
# the index existed.
#
# Context: the fuel engine's idempotency contract is keyed on
# ``(source_type, source_name)`` (one ledger row per originating Fuel Daily Log /
# Fuel Request). The hard backstop is a composite UNIQUE index
# (``unique_fcl_source``) created by
# ``fuel_consumption_ledger.on_doctype_update`` during schema sync. But
# ``frappe.db.add_unique`` issues a bare ``ALTER TABLE ... ADD UNIQUE`` with no
# de-dup, so on a site where two overlapping accrual runs had already double-posted
# a source, that ALTER fails with a Duplicate-entry error and breaks ``bench
# migrate``. This pre-model-sync patch runs BEFORE schema sync (this app's
# patches.txt has no section header, so every entry is pre_model_sync), collapses
# any pre-existing duplicate source rows to the single earliest row, then ensures
# the unique index — so the subsequent schema-sync ``add_unique`` is a no-op and
# migrate stays clean.
#
# Idempotent: re-running finds no duplicates and the index already present, so it
# is a no-op. Existence-guarded on the table so it never raises a schema error
# during migrate, and a no-op on a fresh install (the table holds no duplicates).
# No GL is touched — the ledger is an operational memo. The duplicate rows removed
# here are exact (source_type, source_name) repeats that the engine would itself
# have suppressed; keeping the earliest preserves the originally-ledgered value.


def execute():
    if not frappe.db.table_exists("Fuel Consumption Ledger"):
        return

    # 1) Collapse duplicate (source_type, source_name) rows to the earliest one.
    #    A NULL source_name is never a dedupe key (it is not a real source), so it
    #    is excluded — only genuine, repeated source references are collapsed.
    duplicate_groups = frappe.db.sql(
        """
        SELECT source_type, source_name, COUNT(*) AS n, MIN(creation) AS keep_creation
        FROM `tabFuel Consumption Ledger`
        WHERE source_name IS NOT NULL AND source_name != ''
        GROUP BY source_type, source_name
        HAVING n > 1
        """,
        as_dict=True,
    )

    removed = 0
    for grp in duplicate_groups:
        # Names of every row in the group EXCEPT the earliest (kept) one.
        losers = frappe.db.sql(
            """
            SELECT name FROM `tabFuel Consumption Ledger`
            WHERE source_type = %(st)s AND source_name = %(sn)s
              AND creation > %(keep)s
            """,
            {"st": grp.source_type, "sn": grp.source_name, "keep": grp.keep_creation},
            pluck=True,
        )
        # Guard against ties on `creation` (same timestamp): keep exactly one row
        # of the group, drop the rest, regardless of the > comparison above.
        if len(losers) < (grp.n - 1):
            all_names = frappe.db.sql(
                """
                SELECT name FROM `tabFuel Consumption Ledger`
                WHERE source_type = %(st)s AND source_name = %(sn)s
                ORDER BY creation ASC, name ASC
                """,
                {"st": grp.source_type, "sn": grp.source_name},
                pluck=True,
            )
            losers = all_names[1:]
        for name in losers:
            frappe.db.delete("Fuel Consumption Ledger", {"name": name})
            removed += 1

    if removed:
        frappe.db.commit()
        frappe.logger().info(
            f"dedupe_fuel_ledger: removed {removed} duplicate Fuel Consumption "
            f"Ledger row(s) before applying the unique source index."
        )

    # 2) Ensure the composite UNIQUE index exists. add_unique is itself idempotent
    #    (it checks information_schema and skips if the constraint is present), so
    #    this is a no-op once on_doctype_update has created it. Issuing it here too
    #    means the backstop is guaranteed present after this patch even on the very
    #    first migrate, independent of schema-sync ordering.
    try:
        frappe.db.add_unique(
            "Fuel Consumption Ledger",
            ["source_type", "source_name"],
            constraint_name="unique_fcl_source",
        )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Patch: add unique_fcl_source failed",
        )
        raise

    frappe.db.commit()
