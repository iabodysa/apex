# Copyright (c) 2026, afmcoltd


from __future__ import annotations

import frappe
from frappe.desk.doctype.notification_settings.notification_settings import (
    is_notifications_enabled,
)


LOG_DOCTYPE = "Notification Log"

_SUBJECT_MAX = 140

_SAVEPOINT = "apex_system_notify"


def notify_user_system(
    user: str | None,
    subject: str,
    message: str | None = None,
    *,
    document_type: str | None = None,
    document_name: str | None = None,
) -> bool:
    if not user or not frappe.db.get_value("User", user, "enabled"):
        return False
    if not is_notifications_enabled(user):
        return False
    body = message or subject
    clipped_subject = subject[:_SUBJECT_MAX]
    payload = {
        "doctype": LOG_DOCTYPE,
        "for_user": user,
        "type": "Alert",
        "subject": clipped_subject,
        "email_content": body,
    }
    if document_type and document_name:
        payload["document_type"] = document_type
        payload["document_name"] = document_name
    frappe.db.savepoint(_SAVEPOINT)
    try:
        dedup_filter = {"for_user": user, "type": "Alert", "read": 0}
        if document_type and document_name:
            dedup_filter["document_type"] = document_type
            dedup_filter["document_name"] = document_name
        else:
            dedup_filter["subject"] = clipped_subject
        if frappe.db.exists(LOG_DOCTYPE, dedup_filter):
            return False
        frappe.get_doc(payload).insert()
        return True
    except Exception:
        frappe.db.rollback(save_point=_SAVEPOINT)
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"System notify failed ({user})"[:140],
        )
        return False
