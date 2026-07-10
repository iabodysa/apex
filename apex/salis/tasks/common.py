# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Salis fleet module (split by domain)."""

from __future__ import annotations

import frappe
from frappe import _

from apex.apex_core.utils.operations_alert import insert_operations_alert


BATCH_SIZE = 500


# [#661ibk]
ALERT_DOCTYPE = "Operations Alert"


def _settings_int(fieldname: str, default: int) -> int:
    """Read an Int from the Salis Settings single, falling back to ``default``.

    Thin alias over the canonical ``get_salis_int`` coalesce helper, kept for the
    existing in-module call sites."""
    from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int

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
        from apex.salis.permissions import _project_supervisor

        project = frappe.db.get_value("Salis Vehicle", vehicle, "project")
        return _project_supervisor(project)
    except Exception:
        # [#6uz2xe]
        frappe.log_error(title="Salis: resolve project supervisor failed")
        return None


def _vehicle_project(vehicle: str | None) -> str | None:
    """The vehicle's project, or None. Never raises (a lookup must not abort the job)."""
    if not vehicle:
        return None
    try:
        return frappe.db.get_value("Salis Vehicle", vehicle, "project")
    except Exception:
        # [#tn6dm7]
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
    from frappe.utils import add_days, today

    # [#k7ei2t]
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

    # [#sqhguz] Insert via the shared helper: it applies ignore_permissions, resolves
    # responsible_supervisor from the vehicle's project (same logic as the local
    # _resolve_project_supervisor), clips the message to 2000, and rolls back/log_errors
    # on failure — byte-for-byte the old inline block. A failed/None insert skips the rest.
    alert_name = insert_operations_alert(
        alert_type,
        severity,
        message,
        vehicle=vehicle,
        driver=driver,
    )
    if alert_name is None:
        return None

    # [#oplihr]
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
