# Copyright (c) 2026, afmcoltd

import frappe
from frappe.translate import set_default_language


def execute():
    if frappe.db.get_single_value("System Settings", "language") not in (None, "", "en"):
        return
    if not frappe.db.exists("Language", "ar"):
        return
    frappe.db.set_single_value("System Settings", "language", "ar")
    set_default_language("ar")
