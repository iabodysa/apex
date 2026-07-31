# Copyright (c) 2026, AFMCO and contributors
"""Rename the clearance slip's Print Format row to the surviving DocType name.

The record was stored as "Accommodation Checkout Clearance" for the whole life of the
Accommodation Checkout -> Housing Checkout rename. Its template already prints "Housing
Checkout Clearance"; only the stored key stayed behind, and a Print Format key is what
staff pick from the print dropdown, so the one place the retired name is still read is
the list of formats offered on a Housing Checkout. Unlike the other retired record
names, this one carries no translations/ar.csv row, so an Arabic site shows the stale
English string verbatim rather than a correct Arabic label.

MUST stay in [pre_model_sync]. Print Format is in ``frappe.model.sync``
IMPORTABLE_DOCTYPES (:22), so ``sync_all()`` re-imports the shipped JSON on every
migrate, and ``import_doc`` resolves the record purely by the JSON's ``name`` --
deleting the matching row and re-inserting it (frappe/modules/import_file.py:230-231,
:239). Renaming AFTER that sync is too late: the sync has already inserted the new key
as a second row and left the old one orphaned in the dropdown, and the rename then fails
on the collision. Renaming first means the sync lands on the row this patch just moved.
The re-import always happens: this JSON ships no ``modified`` field, and
``get_datetime(None)`` returns now (frappe/utils/data.py:113-114), so the
``is_db_timestamp_latest`` skip at import_file.py:143 can never fire for it.

NOTHING IS DELETED. ``frappe.rename_doc`` moves the row and repoints every Link field
that referenced the old key -- which is how a site's own Property Setter or
``default_print_format`` on Housing Checkout keeps working. Print Format ships
``allow_rename: 1``, so no force flag is needed.

Idempotent: a fresh install has no old row and this returns without a write; a site that
already renamed likewise. A site somehow carrying BOTH rows is reported rather than
merged, because merging would destroy one of them and that is an owner decision.
"""

from __future__ import annotations

import frappe

DOCTYPE = "Print Format"
OLD = "Accommodation Checkout Clearance"
NEW = "Housing Checkout Clearance"


def execute() -> None:
    old_exists = frappe.db.exists(DOCTYPE, OLD)
    new_exists = frappe.db.exists(DOCTYPE, NEW)

    if old_exists and new_exists:
        frappe.log_error(
            title="Checkout clearance print format duplicated",
            message=(
                f"Both {OLD!r} and {NEW!r} Print Format rows exist. Skipping the rename "
                "so neither is lost. Delete whichever row is unused, then re-run this "
                "patch: bench --site <site> execute "
                "apex.patches.v2_0.rename_checkout_clearance_print_format.execute"
            ),
        )
        return

    if old_exists:
        frappe.rename_doc(DOCTYPE, OLD, NEW)
