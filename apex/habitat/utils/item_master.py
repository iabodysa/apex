# Copyright (c) 2026, afmcoltd
"""Resolving a no-GL stock line's item master fields, in one place.

Four callers denormalise the same triple onto a stock line before it posts or
saves: Accommodation Stock Ledger's own ``post_stock_entry``, and the
``validate`` of Custody Handover, Goods Receipt and Material Transfer, each of
which stamps ``item_name``/``uom`` on its child rows ahead of the ledger post.
``item`` is a Dynamic Link keyed by ``item_type`` (Custody Article or
Maintenance Material), and the two masters name the same three facts
differently — ``article_name``/``unit_of_measure``/``standard_unit_cost`` on
one, ``material_name``/``default_uom``/``estimated_unit_cost`` on the other —
so no ``fetch_from`` can express it: that field option resolves one fixed
source fieldname, not one per possible dynamic-link target. This absorbs what
was a private helper on Accommodation Stock Ledger reached into by the other
three doctypes; a second copy of the ``_MASTER_FIELDS`` map anywhere else is
the field-name split drifting out of sync with what the ledger posts.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt

_MASTER_FIELDS = {
    "Custody Article": ("article_name", "unit_of_measure", "standard_unit_cost"),
    "Maintenance Material": ("material_name", "default_uom", "estimated_unit_cost"),
}


def resolve_item(item_type: str, item: str):
    """Looks up an item's display name, unit of measure and standard cost from its master doctype."""
    fields = _MASTER_FIELDS.get(item_type)
    if not fields:
        return (item, "", 0.0)
    vals = frappe.db.get_value(item_type, item, list(fields), as_dict=True) or {}
    return (vals.get(fields[0]) or item, vals.get(fields[1]) or "", flt(vals.get(fields[2])))
