# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Habitat module (split by domain)."""

from __future__ import annotations

import frappe

from apex.apex_core.utils.operations_alert import insert_operations_alert
from apex.habitat.tasks.common import (
    _notify_operational,
    _notify_role_system,
    _notify_user_system,
)

# One savepoint per nesting level, distinct names: a helper re-using the loop's name
# would REPLACE it mid-iteration and silently destroy the row isolation. Re-issued
# each iteration — MariaDB replaces a same-named savepoint rather than stacking.
_ROW_SAVEPOINT = "safety_row"
_ALERT_SAVEPOINT = "safety_alert_dedupe"


def _raise_safety_alert(alert_type: str, severity: str, message: str, dedupe_token: str) -> str | None:
    """Insert an Operations Alert for a safety obligation breach (idempotent).

    Mirrors _raise_maintenance_alert: existence-guarded on
    ``(alert_type, status=Open, message LIKE %dedupe_token%, raised_on=today)`` so a
    daily job never spams a duplicate. ``alert_type``/``severity`` MUST be valid
    Operations Alert Select options (the DocType's option set is closed). Returns the
    new alert name, or None when a duplicate was skipped or the insert failed.
    """
    from frappe.utils import today

    today_str = today()
    frappe.db.savepoint(_ALERT_SAVEPOINT)
    try:
        if frappe.db.exists(
            "Operations Alert",
            {
                "alert_type": alert_type,
                "status": "Open",
                "message": ["like", f"%{dedupe_token}%"],
                "raised_on": ["between", [f"{today_str} 00:00:00", f"{today_str} 23:59:59"]],
            },
        ):
            return None
    except Exception:
        frappe.db.rollback(save_point=_ALERT_SAVEPOINT)
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Safety alert dedupe check failed ({dedupe_token})"[:140],
        )
        return None

    # Insert via the shared helper (ignore_permissions + message clip + rollback/log_error)
    # — a safety alert carries no vehicle/driver. Returns the new name, or None on failure.
    return insert_operations_alert(alert_type, severity, message)


def _instance_priority(template: str | None) -> str:
    """Resolve a Scheduled Task Instance's effective priority via its template's
    linked Safety Task Catalog task. Returns "" when no priority can be derived."""
    if not template:
        return ""
    catalog = frappe.db.get_value("Scheduled Task Template", template, "safety_task_catalog")
    if not catalog:
        return ""
    return frappe.db.get_value("Safety Task Catalog", catalog, "priority") or ""


def daily_safety_task_compliance_scan() -> None:
    """Daily — flag overdue Scheduled Task Instances Overdue, escalate the urgent ones,
    and flag active buildings with no safety round at all in the recent window.

    An instance counts as overdue once today reaches or passes its due_date plus the
    configured ``safety_overdue_grace_days`` (read as ``value or 0`` — a new Int on the
    Habitat Settings Single may store 0). With zero grace a task is overdue ON its due
    day (``due_date <= cutoff``), not the day after. On flipping an instance to Overdue, the effective
    priority is resolved through its template's Safety Task Catalog task: a High or
    Critical task additionally raises an idempotent Operations Alert AND posts a system
    Notification to the Safety Officer, so urgent safety lapses surface immediately.

    Second pass: every ACTIVE Building (``status == "Active"``) with ZERO
    submitted Safety Rounds of ANY cadence dated within the trailing
    ``ZERO_ROUNDS_WINDOW_DAYS`` raises an idempotent Operations Alert, notifies the
    Safety Officer, posts the reminder to the building timeline, and alerts the
    building's own Responsible Facility Supervisor. This is broader than
    ``weekly_safety_coverage_gate`` (which only
    checks for a *Weekly*-cadence round in the current ISO week): it catches buildings
    with no safety activity whatsoever. The alert carries a ``zero-rounds::<building>``
    dedupe token so daily reruns stay idempotent.

    Per-row error isolation; paginated 500/batch.
    """
    from frappe.utils import today, getdate, add_days

    grace_days = frappe.db.get_single_value("Habitat Settings", "safety_overdue_grace_days") or 0
    cutoff = str(getdate(add_days(today(), -int(grace_days))))
    logger = frappe.logger()

    total_overdue = 0
    escalated = 0

    # [#4qriyf]
    start = 0
    batch_size = 500
    while True:
        overdue = frappe.get_all(
            "Scheduled Task Instance",
            filters={"docstatus": 0, "status": ["in", ["Open", "In Progress"]], "due_date": ["<=", cutoff]},
            fields=["name", "due_date", "template", "building"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not overdue:
            break

        for inst in overdue:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                frappe.db.set_value("Scheduled Task Instance", inst.name, "status", "Overdue")
                _notify_operational(
                    "Scheduled Task Instance", inst.name,
                    f"Scheduled task {inst.name} ({inst.template}) is overdue (was due {inst.due_date}).",
                )
                # [#i4yjwa]
                priority = _instance_priority(inst.template)
                if priority in ("High", "Critical"):
                    msg = (
                        f"daily_safety_task_compliance_scan: {priority}-priority scheduled task "
                        f"{inst.name} ({inst.template}) is overdue (was due {inst.due_date})."
                    )
                    _raise_safety_alert(
                        alert_type="Maintenance Overdue",
                        severity="Critical" if priority == "Critical" else "Warning",
                        message=msg,
                        dedupe_token=inst.name,
                    )
                    _notify_role_system(
                        "Safety Officer",
                        subject=f"Overdue {priority} safety task: {inst.name}",
                        message=msg,
                    )
                    escalated += 1
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Safety compliance scan failed for {inst.name}"[:140],
                )

        total_overdue += len(overdue)
        start += batch_size

    if total_overdue:
        logger.warning(
            f"daily_safety_task_compliance_scan: Marked {total_overdue} Scheduled Task Instances "
            f"as Overdue ({escalated} High/Critical escalated)."
        )
    else:
        logger.info("daily_safety_task_compliance_scan: No overdue instances found.")

    # [#r2zv02]
    ZERO_ROUNDS_WINDOW_DAYS = 7
    window_start = str(getdate(add_days(today(), -ZERO_ROUNDS_WINDOW_DAYS)))
    no_rounds = 0

    start = 0
    while True:
        buildings = frappe.get_all(
            "Building",
            filters={"status": "Active"},
            fields=["name", "building_name", "responsible_supervisor"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not buildings:
            break

        for b in buildings:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                has_round = frappe.db.exists(
                    "Safety Round",
                    {
                        "docstatus": 1,
                        "building": b.name,
                        "round_date": [">=", window_start],
                    },
                )
                if has_round:
                    continue
                label = b.building_name or b.name
                token = f"zero-rounds::{b.name}"
                # [#mpm9mc]
                msg = (
                    f"daily_safety_task_compliance_scan [{token}]: building {label} has no "
                    f"submitted Safety Round in the last {ZERO_ROUNDS_WINDOW_DAYS} days."
                )
                _raise_safety_alert(
                    alert_type="Supervisor Delay",
                    severity="Warning",
                    message=msg,
                    dedupe_token=token,
                )
                _notify_role_system(
                    "Safety Officer",
                    subject=f"No recent safety round: {label}",
                    message=msg,
                    document_type="Building",
                    document_name=b.name,
                )
                # [#76la3e]
                _notify_operational("Building", b.name, msg)
                _notify_user_system(
                    b.responsible_supervisor,
                    subject=f"No recent safety round: {label}",
                    message=msg,
                    document_type="Building",
                    document_name=b.name,
                )
                no_rounds += 1
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Zero-rounds scan failed for {b.name}"[:140],
                )

        start += batch_size

    logger.info(
        f"daily_safety_task_compliance_scan: {no_rounds} active building(s) with no recent safety round."
    )


def weekly_safety_coverage_gate() -> None:
    """Weekly — every ACTIVE building must be covered by a submitted Weekly Safety
    Round this week; flag the buildings that are not.

    Gated by Habitat Settings ``require_weekly_all_building_coverage`` (read as
    ``value if not None else 1`` — the gate defaults ON, but a falsy stored value on
    the Single turns it off, per the Single new-field caveat). When the gate is ON,
    each ACTIVE Building (``status == "Active"``) with no submitted
    Weekly-cadence Safety Round dated within the current ISO week raises an idempotent
    Operations Alert and posts a system Notification to the Safety Officer. Per-row
    error isolation.
    """
    from frappe.utils import today, getdate, add_days

    require_coverage = frappe.db.get_single_value(
        "Habitat Settings", "require_weekly_all_building_coverage"
    )
    require_coverage = require_coverage if require_coverage is not None else 1
    if not require_coverage:
        frappe.logger().info("weekly_safety_coverage_gate: coverage gate disabled — skipping.")
        return

    today_date = getdate(today())
    week_start = add_days(today_date, -today_date.weekday())  # [#sg57er]
    week_end = add_days(week_start, 6)  # [#ezuovy]
    logger = frappe.logger()
    uncovered = 0

    start = 0
    batch_size = 500
    while True:
        buildings = frappe.get_all(
            "Building",
            filters={"status": "Active"},
            fields=["name", "building_name"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not buildings:
            break

        for b in buildings:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                covered = frappe.db.exists(
                    "Safety Round",
                    {
                        "docstatus": 1,
                        "cadence": "Weekly",
                        "building": b.name,
                        "round_date": ["between", [str(week_start), str(week_end)]],
                    },
                )
                if covered:
                    continue
                label = b.building_name or b.name
                msg = (
                    f"weekly_safety_coverage_gate: building {label} ({b.name}) has no submitted "
                    f"Weekly Safety Round for the week of {week_start} — {week_end}."
                )
                logger.warning(msg)
                _raise_safety_alert(
                    alert_type="Supervisor Delay",
                    severity="Warning",
                    message=msg,
                    dedupe_token=b.name,
                )
                _notify_role_system(
                    "Safety Officer",
                    subject=f"Building not covered by a weekly safety round: {label}",
                    message=msg,
                )
                uncovered += 1
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Safety coverage gate failed for {b.name}"[:140],
                )

        start += batch_size

    logger.info(f"weekly_safety_coverage_gate: {uncovered} active building(s) uncovered this week.")


def audit_remediation_deadline_watch() -> None:
    """Daily — flag submitted Client Audit Remediation Plans whose deadline has passed.

    A submitted plan whose ``overall_status`` is not yet closed (anything other than
    "Closed by Client" / "Overdue") and whose ``remediation_deadline`` is before today
    is set to "Overdue", and a system Notification is posted to the plan's AFMCO owner
    and to the Operations Director. Mirrors daily_building_license_expiry_check:
    paginated 500/batch with per-row error isolation.
    """
    from frappe.utils import today, getdate

    today_date = getdate(today())
    logger = frappe.logger()
    flagged = 0

    start = 0
    batch_size = 500
    while True:
        plans = frappe.get_all(
            "Audit Remediation Plan",
            filters={
                "docstatus": 1,
                "overall_status": ["not in", ["Closed by Client", "Overdue"]],
                "remediation_deadline": ["<", str(today_date)],
            },
            fields=["name", "remediation_deadline", "internal_owner", "client_project"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not plans:
            break

        for plan in plans:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                frappe.db.set_value(
                    "Audit Remediation Plan", plan.name, "overall_status", "Overdue"
                )
                msg = (
                    f"audit_remediation_deadline_watch: remediation plan {plan.name} "
                    f"(project {plan.client_project}) passed its deadline {plan.remediation_deadline} "
                    f"and is now Overdue."
                )
                logger.warning(msg)
                _notify_operational("Audit Remediation Plan", plan.name, msg)
                # [#mzdqnr]
                if plan.internal_owner:
                    _notify_user_system(
                        plan.internal_owner,
                        f"Audit remediation overdue: {plan.name}",
                        msg,
                    )
                _notify_role_system(
                    "Operations Director",
                    subject=f"Audit remediation overdue: {plan.name}",
                    message=msg,
                )
                flagged += 1
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Audit remediation watch failed for {plan.name}"[:140],
                )

        start += batch_size

    logger.info(f"audit_remediation_deadline_watch: {flagged} remediation plan(s) flagged Overdue.")
