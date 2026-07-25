# Copyright (c) 2026, AFMCO and contributors
"""Rename the Fleet Workspace row 'fleet' -> 'Fleet' BEFORE the JSON re-imports (A-126).

The shipped salis/workspace/fleet/fleet.json carried ``name: "fleet"`` while its
``label``/``title`` were both "Fleet". That is three separate defects:

  * the Workspace DocType autonames ``field:label``, so the name is meant to BE
    the label -- every other workspace this app ships already obeys that;
  * ``frappe/desk/desktop.py`` builds the boot entry as
    ``page["label"] = _(page.get("name"))``. translations/ar.csv translates
    "Fleet" but not "fleet", so the Arabic Desk showed a raw Latin "fleet" in the
    awesomebar next to properly translated siblings;
  * ``parent_page`` is matched against the parent's TITLE (Workspace.get_children
    and the Desk sidebar both compare ``parent_page == title``), so a name that
    differs from the title is a permanent orphan trap for any future child.

MUST stay in [pre_model_sync]. Workspace sync is import-only: ``import_file``
looks the record up by the JSON's ``name`` and delete+inserts. Running after the
sync is too late -- on PostgreSQL (case-sensitive keys) the sync has already
inserted a second "Fleet" row and left the old "fleet" row orphaned in the
sidebar; on MariaDB (case-insensitive keys) it has already dropped the row and
any User pinned to it. Renaming first means the sync updates the row in place.

``frappe.rename_doc`` is the native path and handles this case explicitly:
validate_rename() clears its "already exists" guard when the collision differs
only by case ("for fixing case, accents"). It also repoints every Link field
pointing at the old key -- notably ``User.default_workspace``. ``parent_page`` is
a plain Data field, so it is repaired separately below.

Idempotent and non-destructive: nothing is ever deleted. If a site already
carries BOTH rows (a PostgreSQL site that migrated before this patch shipped)
the rename is skipped and the duplicate is reported for an owner decision.
"""

from __future__ import annotations

import frappe

OLD = "fleet"
NEW = "Fleet"


def execute() -> None:
    # get_value(doctype, key) returns the STORED name, so comparing it to OLD/NEW
    # is an exact-case probe on both MariaDB (case-insensitive lookup) and
    # PostgreSQL (case-sensitive lookup). A plain db.exists() cannot tell them apart.
    old_row = frappe.db.get_value("Workspace", OLD, "name")
    new_row = frappe.db.get_value("Workspace", NEW, "name")

    if old_row == OLD and new_row == NEW:
        # Two distinct rows. Merging would destroy one; that is an owner decision.
        frappe.log_error(
            title="Fleet workspace duplicated by case",
            message=(
                "Both 'fleet' and 'Fleet' Workspace rows exist. Skipping the rename "
                "so neither is lost. Decide which row to keep, then re-run this patch."
            ),
        )
    elif old_row == OLD:
        frappe.rename_doc("Workspace", OLD, NEW, force=True)

    # parent_page stores the parent's TITLE, so a row still holding the old
    # lowercase key never resolves to a parent and renders nowhere. Compare in
    # Python: a MariaDB filter would match both cases and hide the real state.
    for row in frappe.get_all("Workspace", fields=["name", "parent_page"]):
        if row.parent_page == OLD:
            frappe.db.set_value(
                "Workspace", row.name, "parent_page", NEW, update_modified=False
            )
