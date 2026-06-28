# Copyright (c) 2026, AFMCO and contributors
import frappe


def execute():
    for old_name, new_name in [
        ("Accommodation Goods Receipt", "Goods Receipt"),
        ("Accommodation Custody Handover", "Custody Handover"),
    ]:
        if frappe.db.exists("DocType", old_name):
            frappe.rename_doc("DocType", old_name, new_name, force=True)
