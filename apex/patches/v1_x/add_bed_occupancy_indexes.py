# Copyright (c) 2026, AFMCO and contributors
"""Create the two bed-occupancy indexes on an already-installed Housing Assignment table.

``housing_assignment.on_doctype_update`` declares both indexes, but that hook fires
only from ``DocType.on_update`` — i.e. when the DocType JSON is actually re-imported.
A plain ``bench migrate`` skips a JSON whose hash is unchanged, and the commit that
added the hook touched only the controller, so the JSON hash never moves. The older
``v0_7.add_bed_assignment_index`` patch cannot cover the gap either: a fresh install
marks every registered patch complete without running it, so on any site installed
after that patch was registered it is logged as done while having created nothing.
This patch is the one path that reaches those sites. It delegates to the same guarded
helper under the same index names, so it is a no-op on a site that already has them.

Recorded decision on the redundant ``idx_asgn_bed`` (single column ``bed``): KEEP, do
not drop. ``bed`` is a Link with ``search_index: 1``, so Frappe's own schema sync
normally maintains a single-column index on that column, which makes this one a
duplicate on a freshly created table. But that sync only adds its index when the
column reports as unindexed, so on a site where this patch (or the v0_7 one) won the
race Frappe never created its own — dropping ``idx_asgn_bed`` there would leave the
bed-only access path served only by the leading prefix of the composite, with no
guarantee the framework re-adds a dedicated one. The saving is one small varchar(140)
index; revisit only against a real per-site ``SHOW INDEX`` census.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Housing Assignment"):
        return

    # [#bd7qm2] same index names the controller hook uses, so a site that already
    # has them is a no-op instead of gaining duplicates under a second name.
    from apex.apex_core.utils.ledger_index import add_index_guarded

    add_index_guarded("Housing Assignment", ["bed"], "idx_asgn_bed")
    add_index_guarded(
        "Housing Assignment",
        ["bed", "docstatus", "check_out_date"],
        "idx_asgn_bed_active",
    )
    frappe.db.commit()
