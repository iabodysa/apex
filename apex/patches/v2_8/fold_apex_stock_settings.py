# Copyright (c) 2026, afmcoltd
"""Fold the Apex Stock Settings Single into Habitat Settings and remove it.

One Settings Single per module is the framework's own shape. Six fields —
``enable_stock_engine``, ``require_active_store``, ``allow_negative_stock``,
``backdating_days``, ``backdating_role``, ``stock_frozen_upto`` — sat in a Single of
their own, the least-referenced DocType in the app outside its own directory; they
now live in Habitat Settings' "Stock Engine" tab, and the readers (``policy``,
``validate_posting_allowed``, ``_holds_role``, ``store_is_open``) moved with them
into ``apex.apex_core.doctype.habitat_settings.habitat_settings``. The one
config-time check the source ran on save — a backdating role with a zero-day
window has no effect — moved into ``HabitatSettings.validate``.

Values are carried BEFORE anything is deleted, and read from ``tabSingles``
directly rather than through the document API, because the source DocType is about
to stop existing and because a ``Check`` the operator deliberately set to 0 must
survive: a truthiness test would drop that 0 and let the destination's default
turn the engine, or a guard, back on behind the operator's back.

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


SOURCE = "Apex Stock Settings"
TARGET = "Habitat Settings"
FIELDS = (
    "enable_stock_engine",
    "require_active_store",
    "allow_negative_stock",
    "backdating_days",
    "backdating_role",
    "stock_frozen_upto",
)


def execute():
    """Carry the six stored values, then delete the DocType and its Singles rows.

    The two steps are guarded SEPARATELY on purpose. Deleting the DocType leaves its
    Singles rows behind, so a single early return on the DocType record would skip the
    row cleanup on exactly the site where the first step already ran.
    """
    _carry_values()

    if frappe.db.exists("DocType", SOURCE):
        frappe.delete_doc("DocType", SOURCE, force=True)

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
    operator deliberately cleared, such as turning the stock engine off — and is never
    overwritten, so the fold cannot silently re-enable a posting the operator stopped.

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
