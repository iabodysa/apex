# Copyright (c) 2026, afmcoltd
"""Scheduled tasks for the Habitat module (split by domain)."""

from __future__ import annotations

import frappe

from apex.apex_core.utils.role_assignment import assign_role, reconcile_role_queue
from apex.apex_core.utils.system_notify import notify_user_system
from apex.habitat.doctype.audit_remediation_plan.audit_remediation_plan import (
    refresh_overall_status,
)
from apex.habitat.tasks.common import (
    _notify_operational,
    _notify_role_system,
)

_ROW_SAVEPOINT = "safety_row"

ZERO_ROUNDS_WINDOW_DAYS = 7

SAFETY_ROLE = "Safety Officer"


def _no_recent_round(building):
    """No submitted Safety Round of ANY cadence in the trailing window."""
    from frappe.utils import add_days, getdate, today

    since = str(getdate(add_days(today(), -ZERO_ROUNDS_WINDOW_DAYS)))
    return not frappe.db.exists(
        "Safety Round", {"docstatus": 1, "building": building, "round_date": [">=", since]}
    )


def _uncovered_this_week(building):
    """No submitted Weekly-cadence Safety Round dated inside the current site week."""
    from frappe.utils import get_first_day_of_week, get_last_day_of_week, getdate, today

    today_date = getdate(today())
    span = [str(get_first_day_of_week(today_date)), str(get_last_day_of_week(today_date))]
    return not frappe.db.exists(
        "Safety Round",
        {"docstatus": 1, "building": building, "cadence": "Weekly", "round_date": ["between", span]},
    )


def buildings_needing_safety_attention():
    """Every ACTIVE building failing EITHER safety condition.

    Both jobs reconcile the Building queue against THIS, never against their own pass.
    The framework gives a document one assignment rather than one per reason
    (``assign_to.add`` skips a user who already holds an open ToDo for it), so a job that
    settled only what its own scan found would close the other job's work and the queue
    would depend on which ran last. The two conditions are independent — a building can
    have a Daily round today and no Weekly round this week — so the union is computed,
    never inferred from one.
    """
    return {
        b
        for b in frappe.get_all("Building", filters={"status": "Active"}, pluck="name")
        if _no_recent_round(b) or _uncovered_this_week(b)
    }


def zero_rounds_alert_subject(label: str) -> str:
    """Subject of the daily "no recent safety round" alert for a building.

    Shared with Safety Round's submit-time cleanup: the Safety Officer's copy carries
    no Building link (that role holds no read on Building), so it is deduped and
    cleared by SUBJECT. Producer and clearer must not drift, hence one owner here.
    """
    return f"No recent safety round: {label}"


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
    Critical task is additionally ASSIGNED to every Safety Officer — a native ToDo on the
    instance itself, in the desk queue that role already watches — with a system
    Notification beside it, so urgent safety lapses surface immediately.

    Second pass: every ACTIVE Building (``status == "Active"``) with ZERO
    submitted Safety Rounds of ANY cadence dated within the trailing
    ``ZERO_ROUNDS_WINDOW_DAYS`` is assigned to the Safety Officer, posts the reminder to
    the building timeline, and alerts the building's own Responsible Facility
    Supervisor. This is broader than
    ``weekly_safety_coverage_gate`` (which only
    checks for a *Weekly*-cadence round in the current week): it catches buildings
    with no safety activity whatsoever. Both passes end by reconciling the Building queue
    against ``buildings_needing_safety_attention``, so a building that no longer fails
    EITHER condition has its assignment CLOSED — the half an alert row never had.

    Per-row error isolation; paginated 500/batch.
    """
    from frappe.utils import today, getdate, add_days

    grace_days = frappe.db.get_single_value("Habitat Settings", "safety_overdue_grace_days") or 0
    cutoff = str(getdate(add_days(today(), -int(grace_days))))
    logger = frappe.logger()

    total_overdue, escalated = _flag_overdue_instances(cutoff, logger)
    no_rounds = _flag_buildings_without_rounds(logger)

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
    Weekly-cadence Safety Round dated within the current week is assigned to the
    Safety Officer with a system Notification beside it, and a building covered later
    has that assignment closed on the next run. Per-row
    error isolation.

    """
    from frappe.utils import get_first_day_of_week, get_last_day_of_week, getdate, today

    require_coverage = frappe.db.get_single_value(
        "Habitat Settings", "require_weekly_all_building_coverage"
    )
    require_coverage = require_coverage if require_coverage is not None else 1
    if not require_coverage:
        return

    today_date = getdate(today())
    week_start = get_first_day_of_week(today_date)
    week_end = get_last_day_of_week(today_date)
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
                assign_role("Building", b.name, SAFETY_ROLE, description=msg)
                _notify_role_system(
                    SAFETY_ROLE,
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

    reconcile_role_queue("Building", buildings_needing_safety_attention())

    logger.info(f"weekly_safety_coverage_gate: {uncovered} active building(s) uncovered this week.")


def audit_remediation_deadline_watch() -> None:
    """Daily — flag submitted Client Audit Remediation Plans whose deadline has passed.

    The shared controller rollup decides whether a passed deadline means Overdue or
    whether fully verified actions already close the plan. Newly overdue plans notify
    the internal owner and Accommodation Manager.
    """
    from frappe.utils import today, getdate

    today_date = getdate(today())
    logger = frappe.logger()
    flagged = 0

    cursor = ""
    batch_size = 500
    while True:
        plans = frappe.get_all(
            "Audit Remediation Plan",
            filters={
                "docstatus": 1,
                "overall_status": ["not in", ["Closed by Client", "Overdue"]],
                "remediation_deadline": ["<", str(today_date)],
                "name": [">", cursor],
            },
            fields=["name", "remediation_deadline", "internal_owner", "client_project"],
            order_by="name asc",
            limit_page_length=batch_size,
        )
        if not plans:
            break

        for plan in plans:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                result = refresh_overall_status(plan.name, today_date)
                if result["overall_status"] != "Overdue":
                    continue
                msg = (
                    f"audit_remediation_deadline_watch: remediation plan {plan.name} "
                    f"(project {plan.client_project}) passed its deadline {plan.remediation_deadline} "
                    f"and is now Overdue."
                )
                logger.warning(msg)
                _notify_operational("Audit Remediation Plan", plan.name, msg)
                if plan.internal_owner:
                    notify_user_system(
                        plan.internal_owner,
                        f"Audit remediation overdue: {plan.name}",
                        msg,
                    )
                _notify_role_system(
                    "Accommodation Manager",
                    subject=f"Audit remediation overdue: {plan.name}",
                    message=msg,
                    document_type="Audit Remediation Plan",
                    document_name=plan.name,
                )
                flagged += 1
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Audit remediation watch failed for {plan.name}"[:140],
                )

        cursor = plans[-1].name

    logger.info(f"audit_remediation_deadline_watch: {flagged} remediation plan(s) flagged Overdue.")



def _flag_overdue_instances(cutoff, logger):
    """Flag Scheduled Task Instances past their grace window and escalate the urgent ones.

    Returns (total_overdue, escalated).

    ``frappe.db.savepoint`` / ``rollback`` (frappe/database/database.py:1203, :1186)
    isolate each unit. The one thing a scheduler job cannot afford is a raise reaching
    the top: the worker rolls back the whole run, so every unit already completed is
    lost and the next run repeats them all. The failure is recorded through
    ``frappe.get_traceback`` into the Error Log instead, and the loop carries on.
    """
    total_overdue = 0
    escalated = 0
    queued_instances: list[str] = []

    cursor = ""
    batch_size = 500
    while True:
        overdue = frappe.get_all(
            "Scheduled Task Instance",
            filters={"docstatus": 0, "status": ["in", ["Open", "In Progress"]],
                     "due_date": ["<=", cutoff], "name": [">", cursor]},
            fields=["name", "due_date", "template", "building"],
            order_by="name asc",
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
                priority = _instance_priority(inst.template)
                if priority in ("High", "Critical"):
                    msg = (
                        f"daily_safety_task_compliance_scan: {priority}-priority scheduled task "
                        f"{inst.name} ({inst.template}) is overdue (was due {inst.due_date})."
                    )
                    assign_role(
                        "Scheduled Task Instance",
                        inst.name,
                        SAFETY_ROLE,
                        description=msg,
                        priority="High" if priority == "Critical" else "Medium",
                    )
                    queued_instances.append(inst.name)
                    _notify_role_system(
                        SAFETY_ROLE,
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
        cursor = overdue[-1].name

    if total_overdue:
        logger.warning(
            f"daily_safety_task_compliance_scan: Marked {total_overdue} Scheduled Task Instances "
            f"as Overdue ({escalated} High/Critical escalated)."
        )
    else:
        logger.info("daily_safety_task_compliance_scan: No overdue instances found.")

    reconcile_role_queue("Scheduled Task Instance", queued_instances)
    return total_overdue, escalated


def _flag_buildings_without_rounds(logger):
    """Flag active Buildings with no submitted Safety Round in the trailing window.

    Broader than the weekly coverage gate, which only asks for a Weekly-cadence round
    in the current week — the site's own week, via ``get_first_day_of_week``
    (frappe/utils/data.py:427). This catches a building with no safety activity at all.

    ``frappe.db.savepoint`` / ``rollback`` (frappe/database/database.py:1203, :1186)
    isolate each unit. The one thing a scheduler job cannot afford is a raise reaching
    the top: the worker rolls back the whole run, so every unit already completed is
    lost and the next run repeats them all. The failure is recorded through
    ``frappe.get_traceback`` into the Error Log instead, and the loop carries on.

    The rolling window means a building can stay flagged for many days straight —
    unlike ``audit_remediation_deadline_watch`` and the overdue-instance scan above,
    whose own query filters drop a row the moment it is flagged. The timeline comment
    is therefore written only the pass the building is NEWLY queued to the Safety
    Officer (``assign_role`` returns how many assignees were actually ADDED); the two
    Notification Log sends stay unconditional because ``notify_user_system`` already
    dedupes per user against the unread alert.
    """
    from frappe.utils import add_days, getdate, today

    batch_size = 500
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
                msg = (
                    f"daily_safety_task_compliance_scan [{token}]: building {label} has no "
                    f"submitted Safety Round in the last {ZERO_ROUNDS_WINDOW_DAYS} days."
                )
                newly_assigned = assign_role(
                    "Building", b.name, SAFETY_ROLE, description=msg
                )
                _notify_role_system(
                    SAFETY_ROLE,
                    subject=zero_rounds_alert_subject(label),
                    message=msg,
                )
                if newly_assigned:
                    _notify_operational("Building", b.name, msg)
                notify_user_system(
                    b.responsible_supervisor,
                    subject=zero_rounds_alert_subject(label),
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

    reconcile_role_queue("Building", buildings_needing_safety_attention())
    return no_rounds
