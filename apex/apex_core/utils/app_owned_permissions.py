# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe


def frappe_is_writing_its_own_records() -> bool:
    return bool(
        frappe.flags.in_migrate
        or frappe.flags.in_install
        or frappe.flags.in_patch
        or frappe.flags.in_import
    )
