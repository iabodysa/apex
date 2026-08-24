# Copyright (c) 2026, afmcoltd

import frappe

ALERTS = (
    "Habitat - Rent Payment Due",
    "SIM Operations - Contract Expiry Soon",
)


def execute():
    for name in ALERTS:
        if not frappe.db.exists("Notification", name):
            continue
        if frappe.db.get_value("Notification", name, "enabled"):
            continue
        frappe.db.set_value("Notification", name, "enabled", 1)
