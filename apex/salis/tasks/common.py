# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Salis fleet module (split by domain)."""

from __future__ import annotations

import frappe

from apex.apex_core.utils.role_assignment import assign_role, reconcile_role_queue


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


def _settings_int(fieldname: str, default: int) -> int:
    """Read an Int from the Salis Settings single, falling back to ``default``.

    Thin alias over the canonical ``get_salis_int`` coalesce helper, kept for the
    existing in-module call sites."""
    from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int

    return get_salis_int(fieldname, default)


def _vehicle_project(vehicle: str | None) -> str | None:
    """The vehicle's project, or None. Never raises (a lookup must not abort the job)."""
    if not vehicle:
        return None
    try:
        return frappe.db.get_value("Salis Vehicle", vehicle, "project")
    except Exception:
        frappe.log_error(title="Salis: resolve vehicle project failed")
        return None


def _publish_operations_alert(project: str | None = None) -> None:
    """Signal the operations board to refetch its alert strip/queue. Broadcast to
    the site room; the board filters by project client-side (a None project reloads
    every open board). after_commit so subscribers read committed state. Best-effort:
    a publish failure must never abort the scheduler job."""
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
    """Put a document that needs fleet attention in the Fleet Supervisor queue.

    This replaces an Operations Alert row whose only durable link to its subject was
    a vehicle/driver Link pair plus the record name inside the message text. A native
    assignment IS the link: the ToDo carries reference_type and reference_name, so
    the same document is never queued twice (``assign_to.add`` skips a holder who
    already has an open ToDo for it) and the old per-day dedupe window disappears
    with the row. Severity survives as the ToDo priority so the board can still rank
    the queue. The realtime publish is kept — the operations board listens for it.
    """
    assign_role(
        doctype,
        name,
        FLEET_ROLE,
        description=message[:2000],
        priority=SEVERITY_TO_PRIORITY.get(severity, "Medium"),
    )
    _publish_operations_alert(_vehicle_project(vehicle))
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
    """Post an in-app (system) Notification Log of type Alert to every enabled
    Fleet Supervisor.

    Mirrors habitat.tasks.common._notify_role_system: the notify half of the
    Operations Alert replacement, for a condition that is a completed event or a
    balance rather than pending work a queue could hold open. Per-user delivery via
    the shared system_notify helper (the single Notification Log writer), which
    dedupes on the source doc link per user. No recipients = no-op.
    """
    from frappe.utils.user import get_users_with_role

    from apex.apex_core.utils.system_notify import notify_user_system

    for user in get_users_with_role(FLEET_ROLE) or []:
        notify_user_system(
            user,
            subject,
            message,
            document_type=document_type,
            document_name=document_name,
        )


def _reconcile_queue(doctype: str, still_needing_attention) -> int:
    """Drain the Fleet Supervisor queue for ``doctype`` — the half an alert row
    never had.

    ``still_needing_attention`` must be the UNION across every job that queues this
    DocType (reconcile_role_queue's contract): a document is queued while any
    condition holds and settled only when none does. Publishes the board-refresh
    signal only when something actually drained.
    """
    cleared = reconcile_role_queue(doctype, still_needing_attention)
    if cleared:
        _publish_operations_alert(None)
    return cleared
