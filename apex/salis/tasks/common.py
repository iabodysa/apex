# Copyright (c) 2026, afmcoltd
"""Scheduled tasks for the Salis fleet module (split by domain).

Every ``assign_role`` call here is not a declarative Assignment Rule for the same
reason named in habitat.tasks.safety: a rule picks exactly one user per document
event with no per-document read check (frappe/automation/doctype/assignment_rule/
assignment_rule.py:88-96), while these jobs fan out to every current holder of a
role who can already read the specific document, from a scheduler's own scan.
"""

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
    """The vehicle's project, or None. Never raises (a lookup must not abort the job).

    ``frappe.db.get_value`` (frappe/database/database.py:469) raises on a bad
    query; a scheduler job must survive one failed lookup rather than abort the
    whole pass, which the primitive alone does not guarantee."""
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
    a publish failure must never abort the scheduler job.

    ``frappe.publish_realtime`` (frappe/realtime.py:23) has no try/except of its
    own; a scheduled watcher cannot let a socket-layer failure abort the pass it
    is reporting on."""
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
    ``frappe.db.savepoint`` / ``rollback`` (frappe/database/database.py:1203, :1186)
    isolate each unit. The one thing a plain try/except cannot do is undo a PARTIAL
    write: a row that fails midway leaves what it already inserted, and the next unit
    inherits it. The failure goes to the Error Log through ``frappe.get_traceback``
    and the loop carries on.

    This replaces an alert row whose only durable link to its subject was
    a vehicle/driver Link pair plus the record name inside the message text. A native
    assignment IS the link: the ToDo carries reference_type and reference_name, so
    the same document is never queued twice (``assign_to.add`` skips a holder who
    already has an open ToDo for it) and the old per-day dedupe window disappears
    with the row. Severity survives as the ToDo priority so the board can still rank
    the queue. The realtime publish is kept — the operations board listens for it.

    The comment is written only the first time a document is newly queued
    (``assign_role`` returns how many assignees were actually ADDED). A watcher runs
    daily, so a document already queued is re-seen every pass while its condition
    holds; commenting unconditionally would grow one identical comment per day for
    as long as the queue stayed unresolved, on top of the assignment the operator
    already has open.
    """
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
    """Post an in-app (system) Notification Log of type Alert to every enabled
    Fleet Supervisor.

    Mirrors habitat.tasks.common._notify_role_system, including why it is not a
    declarative Notification: ``receiver_by_role`` resolves with no per-document
    read check (frappe/email/doctype/notification/notification.py:366), and the
    trigger here is a scheduler's own aggregate scan, not one document's own
    save/submit — a condition that is a completed event or a balance rather than
    pending work a queue could hold open. Per-user delivery via the shared
    system_notify helper (the single Notification Log writer), which dedupes on
    the source doc link per user. No recipients = no-op.
    """
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
