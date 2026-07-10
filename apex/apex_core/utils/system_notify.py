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

LOG_DOCTYPE = "Notification Log"

# [#f5xz9g]
_SUBJECT_MAX = 140


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
    ``ignore_permissions``. Best-effort: a failure rolls back and logs but never
    raises, so the calling job keeps running. ``document_type``/``document_name``
    optionally link the alert to its source record (both required to link).
    """
    if not user or not frappe.db.get_value("User", user, "enabled"):
        return False
    body = message or subject
    payload = {
        "doctype": LOG_DOCTYPE,
        "for_user": user,
        "type": "Alert",
        "subject": subject[:_SUBJECT_MAX],
        "email_content": body,
    }
    if document_type and document_name:
        payload["document_type"] = document_type
        payload["document_name"] = document_name
    try:
        frappe.get_doc(payload).insert(ignore_permissions=True)  # audit-ok — scheduler-run system alert
        return True
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"System notify failed ({user})"[:140],
        )
        return False
