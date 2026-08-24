# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils.user import get_users_with_role

from apex.apex_core.utils.role_assignment import assign_role, reconcile_role_queue
from apex.apex_core.utils.system_notify import notify_user_system


BATCH_SIZE = 500

_ALERT_SAVEPOINT = "salis_alert"

FLEET_ROLE = "Fleet Supervisor"

QUEUE_DOCTYPES = (
    "Vehicle Suspension",
    "Salis Vehicle",
    "Salis Driver",
    "Fuel Quota",
    "Rental Office",
)

SEVERITY_TO_PRIORITY = {"Critical": "High", "Warning": "Medium", "Info": "Low"}
PRIORITY_TO_SEVERITY = {"High": "Critical", "Medium": "Warning", "Low": "Info"}


def _vehicle_project(vehicle: str | None) -> str | None:
    if not vehicle:
        return None
    try:
        return frappe.db.get_value("Salis Vehicle", vehicle, "project")
    except Exception:
        frappe.log_error(title="Salis: resolve vehicle project failed")
        return None


def _publish_operations_alert(project: str | None = None) -> None:
    try:
        frappe.publish_realtime("operations_alert", {"project": project}, after_commit=True)
    except Exception:
        pass


def _queue_document(
    doctype: str,
    name: str,
    severity: str,
    message: str,
    vehicle: str | None = None,
) -> None:
    newly_assigned = assign_role(
        doctype,
        name,
        FLEET_ROLE,
        description=message[:2000],
        priority=SEVERITY_TO_PRIORITY.get(severity, "Medium"),
    )
    _publish_operations_alert(_vehicle_project(vehicle))
    if not newly_assigned:
        return
    frappe.db.savepoint(_ALERT_SAVEPOINT)
    try:
        frappe.get_doc(doctype, name).add_comment("Comment", message)
    except Exception:
        frappe.db.rollback(save_point=_ALERT_SAVEPOINT)
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Salis queue comment failed for {name}"[:140],
        )


def _notify_fleet_role(
    subject: str,
    message: str | None = None,
    *,
    document_type: str | None = None,
    document_name: str | None = None,
) -> None:
    for user in get_users_with_role(FLEET_ROLE) or []:
        notify_user_system(
            user,
            subject,
            message,
            document_type=document_type,
            document_name=document_name,
        )


def _reconcile_queue(doctype: str, still_needing_attention) -> int:
    cleared = reconcile_role_queue(doctype, still_needing_attention)
    if cleared:
        _publish_operations_alert(None)
    return cleared
