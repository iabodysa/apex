# Copyright (c) 2026, afmcoltd

import frappe


DOCTYPE = "Salis Settings"

DEFAULTS = {
    "show_brand": 1,
}


def seed_salis_portal_theme():
    if not frappe.db.exists("DocType", DOCTYPE):
        return []

    settings = frappe.get_single(DOCTYPE)
    stored = frappe.db.get_singles_dict(DOCTYPE)
    filled = []
    for field, value in DEFAULTS.items():
        if settings.meta.has_field(field) and field not in stored:
            settings.set(field, value)
            filled.append(field)
    if filled:
        settings.save()
    return filled
