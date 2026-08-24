# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import flt

_MASTER_FIELDS = {
    "Custody Article": ("article_name", "unit_of_measure", "standard_unit_cost"),
    "Maintenance Material": ("material_name", "default_uom", "estimated_unit_cost"),
}


def resolve_item(item_type: str, item: str):
    fields = _MASTER_FIELDS.get(item_type)
    if not fields:
        return (item, "", 0.0)
    vals = frappe.db.get_value(item_type, item, list(fields), as_dict=True) or {}
    return (vals.get(fields[0]) or item, vals.get(fields[1]) or "", flt(vals.get(fields[2])))
