# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe


def has_overlapping_record(
    doctype: str,
    scope_filters: dict,
    start_field: str,
    end_field: str,
    start_value,
    end_value,
    exclude_name: str | None = None,
) -> str | None:
    return frappe.db.get_value(
        doctype,
        {
            **scope_filters,
            "docstatus": ["!=", 2],
            "name": ["!=", exclude_name or ""],
            start_field: ["<=", end_value],
            end_field: [">=", start_value],
        },
        "name",
    )
