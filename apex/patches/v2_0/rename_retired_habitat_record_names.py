# Copyright (c) 2026, AFMCO and contributors
"""Rename the last five stored records still keyed on a retired DocType name.

Two Number Cards, a Dashboard Chart, an Onboarding Step and a Workflow were named after
DocTypes that no longer exist -- Accommodation Assignment, Accommodation Checkout and
Accommodation Lease. Their queries were repointed long ago, so they work; what stayed
behind is the stored key, which is what a user reads on a dashboard card, in the
onboarding tour, and in the workflow shown on a Lease.

MUST stay in [pre_model_sync] for the first four. Onboarding Step is in
``frappe.model.sync`` IMPORTABLE_DOCTYPES and Number Card / Dashboard Chart arrive
through ``sync_dashboards`` (frappe/utils/dashboard.py:113); both resolve a record by the
JSON's ``name``, delete the matching row and re-insert it. Renaming after that sync is
too late -- the sync has already inserted the new key beside the orphaned old one, and
the rename then fails on the collision.

Workflow is the exception and it is the reason this patch exists at all: it is absent
from IMPORTABLE_DOCTYPES, so migrate never reads ``habitat/workflow/**`` and the shipped
JSON alone can never reach a site that already has the row. Its seeder is the only other
writer, and a seeder does not rename.

A Number Card autonames from its ``label`` (frappe number_card.py), so the stored key is
also the translation source string; the ar.csv rows moved with these names in the same
change.

NOTHING IS DELETED. ``frappe.rename_doc`` moves the row and repoints the Link fields
that referenced the old key, which is how a site's own dashboard layout keeps working.
Idempotent: a fresh install has no old row and each rename returns without a write. A
site carrying BOTH keys is reported rather than merged, because merging destroys one of
them and that is an owner decision.

The fourth entry needs ``force``: Onboarding Step ships no ``allow_rename``, so
``validate_rename`` refuses it outright (frappe/model/rename_doc.py:390-391) even though
the record is app-shipped and its new key is the one the module onboarding now names.
force skips ONLY that flag; the write permission check above it still applies.
"""

from __future__ import annotations

import frappe


RENAMES = (
    ("Number Card", "Active Accommodation Assignments", "Active Housing Assignments", False),
    ("Number Card", "Pending Accommodation Checkouts", "Pending Housing Checkouts", False),
    ("Dashboard Chart", "Accommodation Leases by Status", "Leases by Status", False),
    ("Onboarding Step", "Record an Accommodation Assignment", "Record a Housing Assignment", True),
    ("Workflow", "Accommodation Lease Workflow", "Lease Workflow", False),
)


def execute() -> None:
    """Rename each stored record, reporting rather than merging a site that holds both.

    Both probes use the DICT form, not the positional one: ``exists(dt, dn)`` returns
    ``dn`` unqueried whenever ``dn`` equals ``dt``
    (frappe/database/database.py:1259-1261), and both names here are data. The dict form
    is correct in both directions.
    """
    for doctype, old, new, force in RENAMES:
        old_exists = frappe.db.exists(doctype, {"name": old})
        new_exists = frappe.db.exists(doctype, {"name": new})

        if old_exists and new_exists:
            frappe.log_error(
                title="Retired record name duplicated",
                message=(
                    f"Both {old!r} and {new!r} {doctype} rows exist. Skipping this rename "
                    "so neither is lost. Delete whichever row is unused, then re-run: "
                    "bench --site <site> execute "
                    "apex.patches.v2_0.rename_retired_habitat_record_names.execute"
                ),
            )
            continue

        if old_exists:
            frappe.rename_doc(doctype, old, new, force=force)
