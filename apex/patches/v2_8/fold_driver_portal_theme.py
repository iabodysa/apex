# Copyright (c) 2026, afmcoltd

import frappe


SOURCE = "Driver Portal Theme"
TARGET = "Salis Settings"
FIELDS = ("show_brand", "accent_color", "brand_logo")


def execute():
    _carry_values()

    if frappe.db.exists("DocType", SOURCE):
        frappe.delete_doc("DocType", SOURCE, force=True)

    _clear_orphan_singles()


def _carry_values():
    source = frappe.db.get_singles_dict(SOURCE)
    target = frappe.db.get_singles_dict(TARGET)
    for field in FIELDS:
        if field not in source:
            continue
        if target.get(field) not in (None, ""):
            continue
        frappe.db.set_single_value(TARGET, field, source[field])


def _clear_orphan_singles():
    frappe.db.delete("Singles", {"doctype": SOURCE})
