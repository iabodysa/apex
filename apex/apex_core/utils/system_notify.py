# Copyright (c) 2026, afmcoltd

"""In-app system notification helper — the one place that writes a Notification Log row.

The same single-row ``Notification Log`` insert (type Alert, ``subject[:140]``,
best-effort try/rollback/log_error) was copy-pasted across the Habitat safety/audit
scheduler jobs and the Temporary Worker engine. The ``Notification Log`` DocType IS
the native in-app alert primitive; this only factors out the repeated best-effort
system-write boilerplate so a column or default change lives in one place.

The row names a ``for_user`` distinct from the actor writing it — a scheduler job
alerting HR, a driver's own portal action alerting a supervisor, a SIM suspension
alerting SIM Operations — so no single named role covers every caller, and every
future caller of this shared leaf utility would need its own row besides.
``app_owned_permissions_seed.py`` grants ``All`` a ``create`` alongside its existing
native ``read``: Notification Log entries are alerts, not sensitive records, and
``All`` already reads the doctype natively, so this closes the gap at the same
breadth the doctype already ships with rather than naming roles piecemeal.

A leaf utility under ``apex_core`` so any module can import it without coupling
to ``habitat.tasks``.
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
    """Post one in-app (system) Notification Log of type Alert to ONE user.

    Returns ``True`` only when a row was inserted. Falsy or disabled ``user`` is a
    no-op (returns ``False``). Best-effort: a failure rolls back to this call's OWN
    savepoint and logs but never raises, so the caller keeps both the rows it already
    wrote and its own outer savepoint. ``document_type``/``document_name`` optionally
    link the alert to its source record (both required to link).

    Deduped: returns ``False`` without inserting when an UNREAD Alert with the same
    ``for_user`` and dedup key — the source doc link when supplied, else the clipped
    subject — already exists, so a re-running job can't stack duplicate unread bell
    notifications. A different doc or subject stays a distinct alert.

    ``enqueue_create_notification``
    (frappe/desk/doctype/notification_log/notification_log.py:73) is the framework's
    own fan-out and is the right call for a multi-recipient alert. Three things it
    cannot do, and they are why this writes the row directly: it hands the work to a
    background job, so the caller learns nothing about whether a row landed and this
    function's boolean return would be a guess; it never dedupes, so a job that runs
    twice stacks two unread bells; and it returns during install, which is correct
    for it and wrong for a seeder that must know it wrote nothing.

    The savepoint is ``frappe.db.savepoint`` / ``rollback``
    (frappe/database/database.py:1203, :1186) with an OWN named point, so a failure
    here never unwinds the caller's outer savepoint or the rows it already wrote.
    """
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
