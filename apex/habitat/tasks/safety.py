# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    cint,
    get_first_day_of_week,
    get_last_day_of_week,
    getdate,
    today,
)

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

SAFETY_ROLE = "Safety Officer"


def _zero_rounds_window_days() -> int:
    return cint(frappe.db.get_single_value("Habitat Settings", "safety_zero_rounds_window_days")) or 7


def _no_recent_round(building):
    since = str(getdate(add_days(today(), -_zero_rounds_window_days())))
    return not frappe.db.exists(
        "Safety Round", {"docstatus": 1, "building": building, "round_date": [">=", since]}
    )


def _uncovered_this_week(building):
    today_date = getdate(today())
    span = [str(get_first_day_of_week(today_date)), str(get_last_day_of_week(today_date))]
    return not frappe.db.exists(
        "Safety Round",
        {"docstatus": 1, "building": building, "cadence": "Weekly", "round_date": ["between", span]},
    )


def buildings_needing_safety_attention():
    return {
        b
        for b in frappe.get_all("Building", filters={"status": "Active"}, pluck="name")
        if _no_recent_round(b) or _uncovered_this_week(b)
    }


def zero_rounds_alert_subject(label: str) -> str:
    return f"No recent safety round: {label}"


def _instance_priority(template: str | None) -> str:
    if not template:
        return ""
    catalog = frappe.db.get_value("Scheduled Task Template", template, "safety_task_catalog")
    if not catalog:
        return ""
    return frappe.db.get_value("Safety Task Catalog", catalog, "priority") or ""


def daily_safety_task_compliance_scan() -> None:
    grace_days = frappe.db.get_single_value("Habitat Settings", "safety_overdue_grace_days") or 0
    cutoff = str(getdate(add_days(today(), -int(grace_days))))
    logger = frappe.logger()

    total_overdue, escalated = _flag_overdue_instances(cutoff, logger)
    no_rounds = _flag_buildings_without_rounds(logger)

    logger.info(
        f"daily_safety_task_compliance_scan: {no_rounds} active building(s) with no recent safety round."
    )


def weekly_safety_coverage_gate() -> None:
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
                msg = _(
                    "Building {0} ({1}) has no submitted Weekly Safety Round for the "
                    "week of {2} — {3}."
                ).format(label, b.name, week_start, week_end)
                logger.warning(msg)
                assign_role("Building", b.name, SAFETY_ROLE, description=msg)
                _notify_role_system(
                    SAFETY_ROLE,
                    subject=_("Building not covered by a weekly safety round: {0}").format(label),
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
                msg = _(
                    "Remediation plan {0} (project {1}) passed its deadline {2} and is "
                    "now Overdue."
                ).format(plan.name, plan.client_project, plan.remediation_deadline)
                logger.warning(msg)
                _notify_operational("Audit Remediation Plan", plan.name, msg)
                subject = _("Audit remediation overdue: {0}").format(plan.name)
                if plan.internal_owner:
                    notify_user_system(
                        plan.internal_owner,
                        subject,
                        msg,
                    )
                _notify_role_system(
                    "Accommodation Manager",
                    subject=subject,
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
                    _("Scheduled task {0} ({1}) is overdue (was due {2}).").format(
                        inst.name, inst.template, inst.due_date
                    ),
                )
                priority = _instance_priority(inst.template)
                if priority in ("High", "Critical"):
                    msg = _(
                        "{0}-priority scheduled task {1} ({2}) is overdue (was due {3})."
                    ).format(_(priority), inst.name, inst.template, inst.due_date)
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
                        subject=_("Overdue {0} safety task: {1}").format(_(priority), inst.name),
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
    batch_size = 500
    window_days = _zero_rounds_window_days()
    window_start = str(getdate(add_days(today(), -window_days)))
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
                    f"submitted Safety Round in the last {window_days} days."
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
