# Copyright (c) 2026, afmcoltd
"""Fold the Payment Routing Settings Single into Habitat Settings and remove it.

One Settings Single per module is the framework's own shape. Two stored fields —
``target_payment_doctype`` and ``auto_submit_target`` — plus the ``field_map``
child grid sat in a Single of their own; they now live in the Habitat Settings
"Payment Routing" tab, and the config-time refusal that ``PaymentRoutingSettings``
performed on save moved with them into ``HabitatSettings.validate``. The router
itself (``apex.apex_core.payment_router``) reads the same fields off the new home.

The ``router_intro`` "About" panel is NOT carried. It was a read-only Text Editor
whose stored value equalled its own JSON default, and every sentence it held is
stated by a field or section description that moved with the fold, except one
naming a DocType this patch deletes. Its ``tabSingles`` row is cleared with the
rest of the source.

Two kinds of state move here, and the child rows are the half a Singles-only patch
would strand. A Single has no ``tab<Name>`` table, so its scalar values live as rows
in ``tabSingles``; a ``Table`` field on a Single still stores real rows in the CHILD
DocType's own table, keyed by ``parent``/``parenttype``. Deleting the parent DocType
record touches neither: ``frappe.delete_doc("DocType", …)`` routes through
``delete_from_table``, whose Singles branch is reached only when
``doctype != "DocType"`` (``frappe/model/delete_doc.py:207``), and
``Payment Routing Field Map`` is a DocType that survives this fold, so nothing drops
its table either. Both are cleaned explicitly.

``frappe/model/sync.py:172 remove_orphan_doctypes`` deletes the orphan DocType
record on its own during migrate, but leaves both kinds of row behind. This patch
runs in ``post_model_sync``, before that, so it still sees the source and still wins.
"""

import frappe


SOURCE = "Payment Routing Settings"
TARGET = "Habitat Settings"
FIELDS = ("target_payment_doctype", "auto_submit_target")

CHILD_DOCTYPE = "Payment Routing Field Map"
CHILD_FIELD = "field_map"


def execute():
    """Carry the stored values and the field-map rows, then delete the DocType and
    every row it leaves behind.

    The steps are guarded SEPARATELY on purpose. Deleting the DocType leaves its
    ``tabSingles`` rows and its child rows standing, so a single early return on the
    DocType record would skip both cleanups on exactly the site where the first step
    already ran.
    """
    _carry_values()
    _carry_field_map()

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

    ``None`` and ``""`` are the only absences. ``"0"`` is an answer — the ``Check`` an
    operator deliberately cleared to keep routed payments in Draft — and is never
    overwritten, so the fold cannot start auto-submitting payments behind his back.

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


def _carry_field_map():
    """Re-parent the field-map rows onto the destination, or drop them if it has its own.

    A child row belongs to its parent by three columns, so the carry is an UPDATE of
    ``parent``/``parenttype``, not an insert: re-inserting would mint new names and
    lose the ``idx`` order the router applies the mapping in.

    Whichever branch runs, no row keeps the source as its parent. A row pointing at a
    DocType that no longer exists is the same half-removal the orphan ``tabSingles``
    rows are, and it is worse here, because ``field_map`` on a re-created Single would
    silently adopt it.
    """
    if not frappe.db.table_exists(CHILD_DOCTYPE):
        return

    child = frappe.qb.DocType(CHILD_DOCTYPE)
    source_rows = {"parent": SOURCE, "parenttype": SOURCE, "parentfield": CHILD_FIELD}

    if frappe.db.exists(
        CHILD_DOCTYPE, {"parent": TARGET, "parenttype": TARGET, "parentfield": CHILD_FIELD}
    ):
        frappe.db.delete(CHILD_DOCTYPE, source_rows)
        return

    (
        frappe.qb.update(child)
        .set(child.parent, TARGET)
        .set(child.parenttype, TARGET)
        .where(
            (child.parent == SOURCE)
            & (child.parenttype == SOURCE)
            & (child.parentfield == CHILD_FIELD)
        )
    ).run()


def _clear_orphan_singles():
    """Delete the source's ``tabSingles`` rows that the DocType deletion leaves behind."""
    frappe.db.delete("Singles", {"doctype": SOURCE})
