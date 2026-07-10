# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Salis fleet module (split by domain)."""

from __future__ import annotations

import frappe
from frappe import _


BATCH_SIZE = 500


# [#661ibk]
ALERT_DOCTYPE = "Operations Alert"


def _settings_int(fieldname: str, default: int) -> int:
    """Read an Int from the Salis Settings single, falling back to ``default``.

    Thin alias over the canonical ``get_salis_int`` coalesce helper, kept for the
    existing in-module call sites."""
    from apex_habitat.apex_core.doctype.salis_settings.salis_settings import get_salis_int

    return get_salis_int(fieldname, default)


def _resolve_project_supervisor(vehicle: str | None) -> str | None:
    """Resolve the vehicle's project supervisor User, or None.

    Denormalised onto the Operations Alert so the Critical-alert Notification can
    reach the specific project's supervisor (a User Permission holder) — Frappe
    notification recipients cannot follow the vehicle -> project -> supervisor
    chain declaratively. Never raises: a lookup failure must not abort the job.
    """
    if not vehicle:
        return None
    try:
        from apex_habitat.salis.permissions import _project_supervisor

        project = frappe.db.get_value("Salis Vehicle", vehicle, "project")
        return _project_supervisor(project)
    except Exception:
        # Best-effort denorm: never abort the job, but log so a real
        # misconfiguration is not silently invisible.
        frappe.log_error(title="Salis: resolve project supervisor failed")
        return None


def _vehicle_project(vehicle: str | None) -> str | None:
    """The vehicle's project, or None. Never raises (a lookup must not abort the job)."""
    if not vehicle:
        return None
    try:
        return frappe.db.get_value("Salis Vehicle", vehicle, "project")
    except Exception:
        # Best-effort denorm: never abort the job, but log the failure.
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


def _raise_alert(
    alert_type: str,
    severity: str,
    message: str,
    source_doctype: str | None = None,
    source_name: str | None = None,
    vehicle: str | None = None,
    driver: str | None = None,
) -> str | None:
    """Insert an Operations Alert and post a timeline comment on the source doc.

    Idempotent: skips if an Open alert of the same ``alert_type`` for the same
    vehicle/driver already exists today (idempotency key =
    ``(alert_type, vehicle or driver, date(raised_on))``). This prevents the
    daily jobs from spamming duplicate alerts on every run.

    Both the insert and the timeline comment are wrapped so a notify failure
    rolls back and logs but never aborts the calling job.

    Returns the new alert name, or ``None`` if a duplicate was skipped or the
    insert failed.
    """
    from frappe.utils import add_days, now_datetime, today

    # [#91pwgy] raised_on is a Datetime; a "today" window must derive both bounds
    # from ONE today() call. A "<= 23:59:59" upper bound silently drops a row stamped
    # 23:59:59.xxxxxx (the column keeps microseconds), and two separate today() calls
    # could straddle midnight — both reopen the duplicate alert the dedupe suppresses.
    # The upper bound is next-day-midnight (between is inclusive, but now_datetime()
    # never lands on exactly .000000, so tomorrow's first row is not falsely matched).
    day = today()
    dedupe_filters = {
        "alert_type": alert_type,
        "status": "Open",
        "raised_on": ["between", [f"{day} 00:00:00", f"{add_days(day, 1)} 00:00:00"]],
    }
    if vehicle:
        dedupe_filters["vehicle"] = vehicle
    elif driver:
        dedupe_filters["driver"] = driver

    try:
        if frappe.db.exists(ALERT_DOCTYPE, dedupe_filters):
            return None
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Salis alert dedupe check failed ({alert_type})"[:140],
        )
        return None

    # [#sqhguz]
    alert_name = None
    responsible_supervisor = _resolve_project_supervisor(vehicle)
    try:
        alert = frappe.get_doc(
            {
                "doctype": ALERT_DOCTYPE,
                "alert_type": alert_type,
                "severity": severity,
                "status": "Open",
                "raised_on": now_datetime(),
                "vehicle": vehicle,
                "driver": driver,
                "responsible_supervisor": responsible_supervisor,
                "message": message[:2000],
            }
        )
        alert.insert(ignore_permissions=True)  # audit-ok
        alert_name = alert.name
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Salis alert insert failed ({alert_type})"[:140],
        )
        return None

    # Push the operations board to refetch when a new alert lands on a project in
    # view (ahead of its poll). after_commit so subscribers read committed state;
    # client filters by project, so a vehicle-less alert (no project) reloads all.
    _publish_operations_alert(_vehicle_project(vehicle))

    # [#gg8xk4]
    if source_doctype and source_name:
        try:
            frappe.get_doc(source_doctype, source_name).add_comment("Comment", message)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Salis alert comment failed for {source_name}"[:140],
            )

    return alert_name


def _resolve_alert(alert_name: str, reason: str) -> bool:
    """Resolve an Operations Alert: set ``status = Resolved`` and stamp
    ``resolved_on`` + ``resolution_note``, then drop an audit comment.

    Idempotent: an alert that is already ``Resolved`` is left untouched (no
    status flip, no fresh ``resolved_on``, no duplicate comment) so a re-run
    cannot flip-flop the row or rewrite its resolution timestamp. Returns
    ``True`` only when this call performed the resolution. Per-alert error
    isolation is the caller's responsibility.
    """
    from frappe.utils import now_datetime

    current = frappe.db.get_value(ALERT_DOCTYPE, alert_name, "status")
    if current == "Resolved":
        return False

    # [#r0ukij]
    frappe.db.set_value(
        ALERT_DOCTYPE,
        alert_name,
        {
            "status": "Resolved",
            "resolved_on": now_datetime(),
            "resolution_note": reason[:140],
        },
        update_modified=True,
    )
    try:
        frappe.get_doc(ALERT_DOCTYPE, alert_name).add_comment(
            "Info", _("Auto-resolved: {0}").format(reason)
        )
    except Exception:
        # [#qh1i7r]
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Alert resolve comment failed for {alert_name}"[:140],
        )
    return True
