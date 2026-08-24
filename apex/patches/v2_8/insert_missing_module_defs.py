# Copyright (c) 2026, afmcoltd

import frappe
from frappe.installer import add_module_defs


def execute():
    add_module_defs("apex", ignore_if_duplicate=True)
    frappe.clear_cache()
