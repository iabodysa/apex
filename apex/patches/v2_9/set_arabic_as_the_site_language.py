# Copyright (c) 2026, afmcoltd

import frappe
from frappe.translate import set_default_language


def execute():
    chosen = frappe.db.get_single_value("System Settings", "language")
    if chosen in (None, "", "en") and frappe.db.exists("Language", "ar"):
        frappe.db.set_single_value("System Settings", "language", "ar")
        set_default_language("ar")
