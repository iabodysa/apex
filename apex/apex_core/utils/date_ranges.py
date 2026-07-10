# Copyright (c) 2026, AFMCO and contributors
"""Date-range helpers shared across DocTypes."""

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
    """Return the name of an existing ``doctype`` record whose [start, end]
    interval intersects [start_value, end_value] within ``scope_filters``, else
    None.

    Intersection is inclusive on both ends — existing.start <= new.end AND
    existing.end >= new.start — matching the callers' original predicate.
    Cancelled rows (docstatus == 2) and ``exclude_name`` (the row being saved)
    are excluded. Scope semantics stay caller-side: each caller supplies its own
    ``scope_filters`` (e.g. lease scopes by building; utility bill by
    company + building + utility_account) and its own start/end field names.
    """
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
