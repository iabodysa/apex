# Copyright (c) 2026, AFMCO and contributors
"""Add the bed-occupancy performance indexes on Housing Assignment.

MariaDB does not support partial (filtered) unique indexes, so true DB-level
uniqueness for active bed assignments is not achievable here.
Application-level enforcement is in housing_assignment.validate() +
on_submit() SELECT FOR UPDATE.

Both indexes also live in the controller ``on_doctype_update`` (same names, same
columns) so fresh installs — which mark patches complete without running them —
get them too. This patch delegates to the same ``add_index_guarded`` helper, so
an already-migrated site creates them the one idempotent way: a no-op when the
index is already there (under this name or as an equivalent column set), and on
a DDL error a logged ``False`` instead of an exception that would abort the whole
``bench migrate``.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Housing Assignment"):
        return

    from apex.apex_core.utils.ledger_index import add_index_guarded

    # [#44ssmk] [#hb3fq9] `bed` is a Link (varchar 140), so the helper's
    # full-column index is the same index the old `(bed`(140))` DDL created.
    add_index_guarded("Housing Assignment", ["bed"], "idx_asgn_bed")

    # [#cfszw1] [#kx0m7d] serves the active-occupancy check in
    # validate()/on_submit()/on_cancel().
    add_index_guarded(
        "Housing Assignment",
        ["bed", "docstatus", "check_out_date"],
        "idx_asgn_bed_active",
    )

    frappe.db.commit()
