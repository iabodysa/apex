# Copyright (c) 2026, afmcoltd
"""Tell an app-owned write apart from a person's edit.

Several refusals in this app must stand down while Frappe is applying its own shipped
records, or the app's install and migrate would refuse themselves. This module holds that
one test, so the answer is the same wherever it is asked.
"""

from __future__ import annotations

import frappe


def frappe_is_writing_its_own_records() -> bool:
    """True while Frappe is applying shipped records rather than serving a person.

    A refusal that cannot tell the two apart fails the customer's own upgrade. ``validate``
    still runs during a fixture import — ``import_file.py:233`` sets ``ignore_validate``
    only when ``data_import`` is false, and fixtures pass it true — so ``in_import`` has to
    be in this test, not only the three that a migrate or an install would set.
    """
    return bool(
        frappe.flags.in_migrate
        or frappe.flags.in_install
        or frappe.flags.in_patch
        or frappe.flags.in_import
    )
