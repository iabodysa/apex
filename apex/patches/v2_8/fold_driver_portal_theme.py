# Copyright (c) 2026, afmcoltd
"""Fold the Driver Portal Theme Single into Salis Settings and remove it.

One Settings Single per module is the framework's own shape. Three appearance fields —
``show_brand``, ``accent_color``, ``brand_logo`` — sat in a Single of their own beside the
thirty-six that Salis Settings already carried for the same module; they now live in its
"Driver Portal Appearance" section, and the validation that refuses an unsafe accent or
logo moved with them into ``SalisSettings.validate``.

Values are carried BEFORE anything is deleted. A stored value is read from ``tabSingles``
directly rather than through the document API, because the source DocType is about to
stop existing and because a ``Check`` the operator deliberately set to 0 must survive: a
truthiness test would drop that 0 and let the destination's default of 1 silently turn
the brand mark back on.

The cleanup here is NOT a table drop, and that difference is measured rather than assumed.
A Single has no ``tab<Name>`` table at all — ``frappe.db.table_exists`` answers False for
this DocType both before and after deletion — so its values live as rows in ``tabSingles``.
``frappe.delete_doc("DocType", ...)`` routes through ``delete_from_table``, whose Singles
branch is reached only when ``doctype != "DocType"``; deleting the DocType RECORD therefore
takes the other branch and leaves every ``tabSingles`` row standing. Those orphan rows are
the half-removal this patch exists to avoid, and clearing them is the cleanup a table drop
would be for an ordinary DocType.

Deleting the JSON alone would leave the DocType record and its Singles rows behind on
every site that already migrated, so the removal has to run here.
"""

import frappe


SOURCE = "Driver Portal Theme"
TARGET = "Salis Settings"
FIELDS = ("show_brand", "accent_color", "brand_logo")


def execute():
    """Carry the three stored values, then delete the DocType and its Singles rows.

    The three steps are guarded SEPARATELY on purpose. Deleting the DocType leaves its
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
    a Single writes a row for EVERY field including the ones nobody filled — measured: one
    ``save`` of the destination leaves ``accent_color`` and ``brand_logo`` sitting in
    ``tabSingles`` as NULL. Treating those rows as "already set" would skip the carry and
    strand the values in the source with nothing to report.

    ``None`` and ``""`` are the only absences. ``"0"`` is an answer — a ``Check`` the
    operator deliberately cleared — and is never overwritten, and never dropped on the
    source side either, so the destination's default of 1 cannot turn the brand mark back
    on behind the operator's back.
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
