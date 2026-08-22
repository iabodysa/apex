# Copyright (c) 2026, afmcoltd
"""Shared ground for the seeders that fill a Single's defaults on install and migrate."""

import frappe


def never_stored(doctype: str, field: str) -> bool:
    """True when the Single holds no row for ``field`` at all.

    Frappe writes every field of a Single to ``tabSingles`` on save, including a Check
    left at 0, so the presence of a row is what separates an answer from a silence.
    A seeder that tests falsiness instead cannot tell "the administrator turned this
    off" from "nobody has said yet", and re-forces every deliberate off back on at the
    next migrate — which is silent, because the value it writes is a legitimate default.
    """
    return not frappe.db.sql(
        "select 1 from tabSingles where doctype = %s and field = %s limit 1",
        (doctype, field),
    )
