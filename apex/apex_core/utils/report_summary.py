# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from frappe.utils import flt


def card(label, value, datatype="Int", indicator=None, options=None):
    entry = {"label": label, "value": value, "datatype": datatype}
    if indicator:
        entry["indicator"] = indicator
    if options:
        entry["options"] = options
    return entry


def count_card(label, rows, predicate=None, indicator=None):
    value = len([r for r in rows if predicate(r)]) if predicate else len(rows)
    return card(label, value, "Int", indicator)


def total_card(label, rows, fieldname, datatype="Float", indicator=None, options=None):
    total = sum(flt(r.get(fieldname)) for r in rows)
    return card(label, round(total, 2), datatype, indicator, options)


def percent_card(label, numerator, denominator, indicator=None):
    pct = round((numerator / denominator) * 100, 1) if denominator else 0.0
    return card(label, pct, "Percent", indicator)
