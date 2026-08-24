# Copyright (c) 2026, afmcoltd


from __future__ import annotations

import frappe
from frappe.desk.doctype.notification_settings.notification_settings import (
    is_email_notifications_enabled,
)


def mailable(users) -> list[str]:
    out = []
    for user in users or []:
        if not user or user in ("Administrator", "Guest"):
            continue
        enabled = frappe.db.get_value("User", user, "enabled")
        if enabled is None:
            out.append(user)
            continue
        if not enabled:
            continue
        if not is_email_notifications_enabled(user):
            continue
        out.append(user)
    return out
