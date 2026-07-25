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

    # [#44ssmk] [#cfszw1] Delegate to the controller declaration — one source for
    # the index names and column sets, so this patch and the fresh-install path
    # cannot drift apart. `bed` is a Link (varchar 140), so the helper's
    # full-column index is the same index the old `(bed`(140))` DDL created.
    from apex.habitat.doctype.housing_assignment import housing_assignment

    housing_assignment.on_doctype_update()

    frappe.db.commit()
