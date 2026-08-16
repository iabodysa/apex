# Copyright (c) 2026, afmcoltd
"""Scheduled tasks for the Habitat module (split by domain)."""

from __future__ import annotations

import frappe

_SAVEPOINT = "apex_notify_operational"


def _notify_operational(source_doctype: str, source_name: str, message: str) -> None:
    """Post an operational notice to the source document's timeline, gated by the
    Habitat Settings "Enable Operational Notifications" toggle.

    This replaces the deprecated Operations Alert inserts: native Frappe
    timeline Comments (plus the configured Notification emails) carry operational
    notices. When the toggle is OFF the scheduler jobs run silently. Technical
    exceptions go to the standard Error Log, not here.
    """
    if not frappe.db.get_single_value("Habitat Settings", "enable_operational_notifications"):
        return
    if not (source_doctype and source_name):
        return
    frappe.db.savepoint(_SAVEPOINT)
    try:
        frappe.get_doc(source_doctype, source_name).add_comment("Comment", message)
    except Exception:
        frappe.db.rollback(save_point=_SAVEPOINT)
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Operational notification comment failed for {source_name}"[:140],
        )


def _notify_role_system(
    role: str,
    subject: str,
    message: str | None = None,
    *,
    document_type: str | None = None,
    document_name: str | None = None,
) -> None:
    """Post an in-app (system) Notification Log of type Alert to every enabled user
    holding ``role``.

    Mirrors temporary_worker_engine._notify_hr: the in-desk alert the Wave-3 safety
    jobs raise for the Safety Officer / Operations Director. Best-effort — a failure
    rolls back to the helper's own savepoint and logs, so the calling job keeps both
    its earlier rows and its own savepoint. No recipients = no-op.
    Per-user delivery via the shared system_notify helper (the single Notification
    Log writer). Optional ``document_type``/``document_name`` link the alert to its
    source record, which is also the helper's per-user dedup key.
    """
    from frappe.utils.user import get_users_with_role

    from apex.apex_core.utils.system_notify import notify_user_system

    for user in get_users_with_role(role) or []:
        notify_user_system(
            user,
            subject,
            message,
            document_type=document_type,
            document_name=document_name,
        )


def _notify_user_system(
    user: str | None,
    subject: str,
    message: str | None = None,
    *,
    document_type: str | None = None,
    document_name: str | None = None,
) -> None:
    """Post an in-app (system) Notification Log of type Alert to ONE specific user.

    Single-recipient sibling of _notify_role_system, for reaching the building's own
    responsible supervisor specifically (not the whole role). Falsy/disabled user = no-op.
    Thin wrapper over the shared system_notify helper. Optional ``document_type``/
    ``document_name`` link the alert to its source record, which is also the helper's
    per-user dedup key.
    """
    from apex.apex_core.utils.system_notify import notify_user_system

    notify_user_system(
        user,
        subject,
        message,
        document_type=document_type,
        document_name=document_name,
    )
