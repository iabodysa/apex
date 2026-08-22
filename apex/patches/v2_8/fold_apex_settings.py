# Copyright (c) 2026, afmcoltd
"""Fold the Apex Settings Single into Habitat Settings and remove it.

One Settings Single per module is the framework's own shape. Three fields —
``enable_gl_posting``, ``snapshot_retention_days``,
``depreciation_snapshot_retention_days`` — sat in a Single of their own beside the
twenty-four Habitat Settings already carried; they now live in its "Financial
Posting" and "Data Retention" sections, and the readers
(``retention_days``, ``effective_retention_days``, ``gl_posting_enabled``) moved
with them into ``apex.apex_core.doctype.habitat_settings.habitat_settings``.

Values are carried BEFORE anything is deleted, and read from ``tabSingles``
directly rather than through the document API, because the source DocType is about
to stop existing and because a ``Check`` the operator deliberately set to 0 must
survive: a truthiness test would drop that 0 and let the destination's default
decide the finance gate instead of the operator.

The cleanup here is NOT a table drop. A Single has no ``tab<Name>`` table at all —
``frappe.db.table_exists`` answers False for this DocType both before and after
deletion — so its values live as rows in ``tabSingles``.
``frappe.delete_doc("DocType", ...)`` routes through ``delete_from_table``, whose
Singles branch is reached only when ``doctype != "DocType"``
(``frappe/model/delete_doc.py:207``); deleting the DocType RECORD therefore takes
the other branch and leaves every ``tabSingles`` row standing. Those orphan rows
are the half-removal this patch exists to avoid.

``frappe/model/sync.py:172 remove_orphan_doctypes`` deletes the orphan DocType
record on its own during migrate, but leaves the value rows behind. This patch runs
in ``post_model_sync``, before that, so it still sees the source and still wins.
"""

import frappe


SOURCE = "Apex Settings"
TARGET = "Habitat Settings"
FIELDS = (
    "enable_gl_posting",
    "snapshot_retention_days",
    "depreciation_snapshot_retention_days",
)


def execute():
    """Carry the three stored values, then delete the DocType and its Singles rows.

    The three steps are guarded SEPARATELY on purpose. Deleting the DocType leaves its
    Singles rows behind, so a single early return on the DocType record would skip the
    row cleanup on exactly the site where the first step already ran.
    """
    _carry_values()

    if frappe.db.exists("DocType", SOURCE):
        frappe.delete_doc("DocType", SOURCE, force=True, ignore_permissions=True)

    _clear_orphan_singles()


def _carry_values():
    """Copy each stored source value onto a destination that does not hold one yet.

    Re-running moves nothing: the first run clears the source rows, so every later read
    finds no key and skips. That is the whole idempotency guarantee. The destination test
    only stops the patch clobbering a value somebody already set.

    That destination test reads the VALUE and not the presence of the row, because saving
    a Single writes a row for EVERY field including the ones nobody filled. Treating those
    rows as "already set" would skip the carry and strand the values in the source with
    nothing to report.

    ``None`` and ``""`` are the only absences. ``"0"`` is an answer — a ``Check`` the
    operator deliberately cleared — and is never overwritten, so the destination cannot
    turn the GL-posting gate back on behind the operator's back.

    ``frappe.db.get_singles_dict`` is the read, not ``frappe.db.get_value("Singles", …)``:
    that table carries no ``modified`` column for the ORDER BY to name, so the ordinary
    getter raises on it.
    """
    source = frappe.db.get_singles_dict(SOURCE)
    target = frappe.db.get_singles_dict(TARGET)
    for field in FIELDS:
        if field not in source:
            continue
        if target.get(field) not in (None, ""):
            continue
        frappe.db.set_single_value(TARGET, field, source[field])


def _clear_orphan_singles():
    """Delete the source's ``tabSingles`` rows that the DocType deletion leaves behind."""
    frappe.db.delete("Singles", {"doctype": SOURCE})
