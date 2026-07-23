# Copyright (c) 2026, AFMCO and contributors
import frappe

_NOTIFICATIONS = (
    "Salis - Vehicle Theft Reported",
    "Salis - Workshop Overstay",
)


def execute():
    # [#qfm9kh]
    for name in _NOTIFICATIONS:
        if not frappe.db.exists("Notification", name):
            continue
        current = frappe.db.get_value(
            "Notification", name, ["enabled", "send_system_notification"], as_dict=True
        )
        if current.enabled and current.send_system_notification:
            continue
        frappe.db.set_value(
            "Notification",
            name,
            {"enabled": 1, "send_system_notification": 1},
            update_modified=False,
        )
