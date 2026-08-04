# Copyright (c) 2026, AFMCO and contributors

"""Shared Query-Report helpers.

Deduplicates boilerplate that recurred verbatim across the Salis/Habitat query
reports. Each helper returns a value the caller assigns itself, so every report
keeps its own field name and its own short-circuit — only the shared fragment
moves here. Behaviour is byte-identical to the inlined blocks it replaces.

Use date_range_condition() from apex_core/utils/report_helpers.py instead of
re-implementing the from/to filter block.
"""

import frappe


def date_range_condition(filters, field, from_key="from_date", to_key="to_date"):
    """Return the frappe.get_all filter fragment for a from/to date range.

    `field` names the condition key the caller will assign the fragment to; it is
    part of the call for readability/symmetry with `conditions[field] = <...>`.

    Returns, matching the historical inline block exactly:
      - ["between", [from, to]] when both bounds are set,
      - [">=", from]            when only the lower bound is set,
      - ["<=", to]              when only the upper bound is set,
      - None                    when neither is set (caller skips the key).
    """
    from_value = filters.get(from_key)
    to_value = filters.get(to_key)
    if from_value and to_value:
        return ["between", [from_value, to_value]]
    if from_value:
        return [">=", from_value]
    if to_value:
        return ["<=", to_value]
    return None


def scoped_names(doctype, allowed, filter_field="project", pluck="name"):
    """Resolve the in-scope master names for a permission-restricted report.

    Wraps the `frappe.get_all(doctype, filters={<field>: ["in", allowed]},
    pluck=...)` lookup that every scoped report repeated. The caller keeps its own
    result variable and its own "empty → return columns, []" short-circuit; only
    this lookup moves here.
    """
    return frappe.get_all(doctype, filters={filter_field: ["in", allowed]}, pluck=pluck)
