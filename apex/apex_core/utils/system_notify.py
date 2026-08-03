# Copyright (c) 2026, AFMCO and contributors

"""In-app system notification helper — the one place that writes a Notification Log row.

The same single-row ``Notification Log`` insert (type Alert, ``subject[:140]``,
``ignore_permissions``, best-effort try/rollback/log_error) was copy-pasted across
the Habitat safety/audit scheduler jobs and the Temporary Worker engine. The
``Notification Log`` DocType IS the native in-app alert primitive; this only factors
out the repeated best-effort system-write boilerplate so a column or default change
lives in one place.

Mirrors ``operations_alert.insert_operations_alert``: a leaf utility under
``apex_core`` so any module can import it without coupling to ``habitat.tasks``.
Callers keep their own recipient resolution (role lookups are domain-specific) and
loop this per user. Best-effort by design — a Notification Log failure must never
abort the calling scheduler job; for request-path sends that should surface errors,
insert the row directly instead.
"""

from __future__ import annotations

import frappe
from frappe.desk.doctype.notification_settings.notification_settings import (
    is_notifications_enabled,
)

LOG_DOCTYPE = "Notification Log"

# [#f5xz9g]
_SUBJECT_MAX = 140

# Every caller loops this per user, so recovery must be row-scoped. A bare
# frappe.db.rollback() would discard the caller's whole run AND destroy the
# per-row savepoint it set, leaving a later rollback to hit MariaDB 1305.
_SAVEPOINT = "apex_system_notify"


def notify_user_system(
    user: str | None,
    subject: str,
    message: str | None = None,
    *,
    document_type: str | None = None,
    document_name: str | None = None,
) -> bool:
    """Post one in-app (system) Notification Log of type Alert to ONE user.

    Returns ``True`` only when a row was inserted. Falsy or disabled ``user`` is a
    no-op (returns ``False``). System-written from scheduler jobs, so
    ``ignore_permissions``. Best-effort: a failure rolls back to this call's OWN
    savepoint and logs but never raises, so the caller keeps both the rows it already
    wrote and its own outer savepoint. ``document_type``/``document_name`` optionally
    link the alert to its source record (both required to link).

    Deduped: returns ``False`` without inserting when an UNREAD Alert with the same
    ``for_user`` and dedup key — the source doc link when supplied, else the clipped
    subject — already exists, so a re-running job can't stack duplicate unread bell
    notifications. A different doc or subject stays a distinct alert.
    """
    if not user or not frappe.db.get_value("User", user, "enabled"):
        return False
    # `User.enabled` is the LOGIN flag, not the notification one. A user who turned
    # notifications off in their own settings kept receiving every Apex alert, because
    # nothing here read the switch that owns that answer.
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
        # [#a069dd] Skip a duplicate UNREAD alert so a re-running job (e.g. the daily zero-rounds
        # scan) can't stack bell notifications: key on the source doc link, else the subject —
        # a different building/subject stays distinct. Cleared on read or on resolve.
        dedup_filter = {"for_user": user, "type": "Alert", "read": 0}
        if document_type and document_name:
            dedup_filter["document_type"] = document_type
            dedup_filter["document_name"] = document_name
        else:
            dedup_filter["subject"] = clipped_subject
        if frappe.db.exists(LOG_DOCTYPE, dedup_filter):
            return False
        frappe.get_doc(payload).insert(ignore_permissions=True)  # audit-ok — scheduler-run system alert
        return True
    except Exception:
        frappe.db.rollback(save_point=_SAVEPOINT)
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"System notify failed ({user})"[:140],
        )
        return False
