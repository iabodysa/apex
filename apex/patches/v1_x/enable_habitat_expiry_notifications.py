# Copyright (c) 2026, AFMCO and contributors
import frappe

# P-204: the expiry-watcher notify boilerplate was replaced by these native
# Notifications. They shipped enabled:0 as scaffolding; Notification.enabled is in
# import_file.ignore_values, so migrate preserves the stale DB value and never applies
# the JSON enabled flip. Flip enabled + send_system_notification on the live rows.
_NOTIFICATIONS = (
    "Habitat - Building License Expiring Soon",
    "Habitat - Building License Expired",
    "Habitat - Building Lease Expiring",
    "Habitat - Building Lease Expired",
    "Habitat - Temporary Stay Ending",
    "Habitat - Temporary Stay Overdue",
)


def execute():
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
