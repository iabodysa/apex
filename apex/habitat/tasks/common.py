# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils.user import get_users_with_role

from apex.apex_core.utils.system_notify import notify_user_system

_SAVEPOINT = "apex_notify_operational"


def _notify_operational(source_doctype: str, source_name: str, message: str) -> None:
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
    for user in get_users_with_role(role) or []:
        notify_user_system(
            user,
            subject,
            message,
            document_type=document_type,
            document_name=document_name,
        )
