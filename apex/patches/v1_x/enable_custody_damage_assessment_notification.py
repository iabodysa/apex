# Copyright (c) 2026, AFMCO and contributors
import frappe

_NOTIFICATION = "Habitat - Custody Damage Assessment Created"


def execute():
    # [#qfm9kh]
    if not frappe.db.exists("Notification", _NOTIFICATION):
        return

    current = frappe.db.get_value(
        "Notification",
        _NOTIFICATION,
        ["enabled", "send_system_notification"],
        as_dict=True,
    )
    if current.enabled and current.send_system_notification:
        return

    frappe.db.set_value(
        "Notification",
        _NOTIFICATION,
        {"enabled": 1, "send_system_notification": 1},
        update_modified=False,
    )
