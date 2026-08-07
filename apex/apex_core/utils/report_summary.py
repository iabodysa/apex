# Copyright (c) 2026, AFMCO and contributors
"""The number strip at the top of a query report.

`frappe.desk.query_report` reads a fifth return value from `execute` and renders each
entry as a card above the table (`query_report.py:87`). Every Apex report returned two
values, so that strip was empty on all of them and a reader had to add the column up
themselves to learn anything the rows did not already say.

The figures are built here rather than in each report so the shape cannot drift across
fifty-two of them, and so a summary reads the SAME rows the table shows — a strip
computed from its own query would eventually disagree with the table under it, and the
reader has no way to tell which one is wrong.
"""

from __future__ import annotations

from frappe.utils import flt


def card(label, value, datatype="Int", indicator=None, options=None):
    """One figure on the strip. ``indicator`` colours it: Green, Orange, Red, Blue."""
    entry = {"label": label, "value": value, "datatype": datatype}
    if indicator:
        entry["indicator"] = indicator
    if options:
        entry["options"] = options
    return entry


def count_card(label, rows, predicate=None, indicator=None):
    """How many rows match, or how many there are. Counts the rows ALREADY on screen."""
    value = len([r for r in rows if predicate(r)]) if predicate else len(rows)
    return card(label, value, "Int", indicator)


def total_card(label, rows, fieldname, datatype="Float", indicator=None, options=None):
    """The column total, summed off the same rows the table renders."""
    total = sum(flt(r.get(fieldname)) for r in rows)
    return card(label, round(total, 2), datatype, indicator, options)


def percent_card(label, numerator, denominator, indicator=None):
    """A share, guarded against the empty report — an empty table reads 0%, never a
    division error and never a blank card that looks like a failure."""
    pct = round((numerator / denominator) * 100, 1) if denominator else 0.0
    return card(label, pct, "Percent", indicator)
