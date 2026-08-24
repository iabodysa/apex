# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import (
    get_first_day,
    get_first_day_of_week,
    get_last_day,
    get_last_day_of_week,
    get_quarter_ending,
    get_quarter_start,
    get_year_ending,
    get_year_start,
    getdate,
    nowdate,
)
from frappe.utils.user import get_users_with_role

from apex.apex_core.utils.email_gate import mailable
from apex.habitat.permissions import validate_building_scope

_SCOPE_BASE = {"is_active": 1}

_CADENCE_ORDER = ["Daily", "Weekly", "Monthly", "Quarterly", "Annual"]

_TASK_FIELDS = [
    "name",
    "task_code",
    "task_title",
    "department",
    "priority",
    "instructions",
    "evidence_required",
]


@frappe.whitelist()
def get_tasks_for_cadence(building, cadence):
    frappe.has_permission("Safety Task Catalog", "read", throw=True)

    if not cadence:
        frappe.throw(_("A cadence is required to build the checklist."))
    if not building:
        frappe.throw(_("A building is required to build the checklist."))
    frappe.has_permission("Building", "read", doc=building, throw=True)

    return {
        "building": building,
        "cadence": cadence,
        "tasks": _scoped_tasks(building, cadence),
    }


def _scoped_tasks(building, cadence):
    base = {**_SCOPE_BASE, "frequency": cadence}

    tasks = {}
    for t in frappe.get_all(
        "Safety Task Catalog",
        filters={**base, "applicable_to_all_buildings": 1},
        fields=_TASK_FIELDS,
    ):
        tasks[t.name] = t

    scoped_parents = frappe.get_all(
        "Safety Task Building Scope",
        filters={"parenttype": "Safety Task Catalog", "building": building},
        pluck="parent",
    )
    if scoped_parents:
        for t in frappe.get_all(
            "Safety Task Catalog",
            filters={
                **base,
                "applicable_to_all_buildings": 0,
                "name": ["in", scoped_parents],
            },
            fields=_TASK_FIELDS,
        ):
            tasks.setdefault(t.name, t)

    return sorted(tasks.values(), key=lambda t: str(t.get("task_code") or t.name))


def _current_period(cadence, on_date=None):
    day = getdate(on_date or nowdate())

    if cadence == "Daily":
        return day, day, {"kind": "day"}

    if cadence == "Weekly":
        start = getdate(get_first_day_of_week(day))
        end = getdate(get_last_day_of_week(day))
        return start, end, {"kind": "week"}

    if cadence == "Monthly":
        start = getdate(get_first_day(day))
        end = getdate(get_last_day(day))
        return start, end, {"kind": "month", "month": start.month, "year": start.year}

    if cadence == "Quarterly":
        start = getdate(get_quarter_start(day))
        end = getdate(get_quarter_ending(day))
        quarter = (day.month - 1) // 3 + 1
        return start, end, {"kind": "quarter", "quarter": quarter, "year": day.year}

    if cadence == "Annual":
        start = getdate(get_year_start(day))
        end = getdate(get_year_ending(day))
        return start, end, {"kind": "year", "year": day.year}

    frappe.throw(_("Unknown cadence: {0}").format(cadence))


def _cadence_is_due(building, cadence, on_date=None):
    start, end, _period = _current_period(cadence, on_date)
    existing = frappe.db.exists(
        "Safety Round",
        {
            "building": building,
            "cadence": cadence,
            "docstatus": ["<", 2],
            "round_date": ["between", [start, end]],
        },
    )
    return not existing


@frappe.whitelist()
def get_due_cadences(building=None):
    frappe.has_permission("Safety Task Catalog", "read", throw=True)

    if not building:
        frappe.throw(_("A building is required to compute due cadences."))
    frappe.has_permission("Building", "read", doc=building, throw=True)

    due = []
    for cadence in _CADENCE_ORDER:
        if not _cadence_is_due(building, cadence):
            continue
        tasks = _scoped_tasks(building, cadence)
        if not tasks:
            continue
        _start, _end, period = _current_period(cadence)
        due.append({"cadence": cadence, "period": period, "tasks": tasks})

    return {"building": building, "due": due, "awaiting": _awaiting_ratification(building)}


def _awaiting_ratification(building) -> list:
    out = []
    for cadence in _CADENCE_ORDER:
        start, end, period = _current_period(cadence)
        row = frappe.db.get_value(
            "Safety Round",
            {
                "building": building,
                "cadence": cadence,
                "docstatus": 0,
                "round_date": ["between", [start, end]],
            },
            ["name", "round_date"],
            as_dict=True,
        )
        if row:
            out.append(
                {
                    "cadence": cadence,
                    "period": period,
                    "round": row.name,
                    "round_date": str(row.round_date),
                }
            )
    return out


@frappe.whitelist(methods=["POST"])
def submit_round(building, cadence, round_date, lines, is_reinspection=0):
    frappe.has_permission("Safety Task Execution", "submit", throw=True)
    frappe.has_permission("Building", "read", doc=building, throw=True)

    if not building:
        frappe.throw(_("A building is required to submit a round."))
    if not cadence:
        frappe.throw(_("A cadence is required to submit a round."))
    if cadence not in _CADENCE_ORDER:
        frappe.throw(_("Unknown cadence: {0}").format(cadence))
    if not round_date:
        frappe.throw(_("A round date is required to submit a round."))

    try:
        lines = frappe.parse_json(lines)
    except ValueError:
        frappe.throw(_("Checklist lines must be valid JSON."))
    if not isinstance(lines, list):
        frappe.throw(_("Checklist lines must be a list."))

    is_reinspection = 1 if frappe.utils.cint(is_reinspection) else 0

    round_doc, count = _create_round(
        building, cadence, round_date, lines, is_reinspection
    )

    round_doc.reload()
    return {
        "ok": True,
        "safety_round": round_doc.name,
        "overall_result": round_doc.overall_result,
        "count": count,
    }


def _create_round(building, cadence, round_date, lines, is_reinspection, ratify=True):
    savepoint = f"safety_checklist_round_{frappe.scrub(cadence)}"
    frappe.db.savepoint(savepoint)
    try:
        round_doc = frappe.get_doc(
            {
                "doctype": "Safety Round",
                "building": building,
                "round_date": round_date,
                "cadence": cadence,
                "supervisor": frappe.session.user,
                "is_reinspection": is_reinspection,
            }
        )
        round_doc.insert(ignore_permissions=False)

        count = 0
        for line in lines:
            task = line.get("task")
            execution_status = line.get("execution_status")
            if not task or not execution_status:
                frappe.throw(
                    _("Each checklist line needs a task and an execution status.")
                )
            ste = frappe.get_doc(
                {
                    "doctype": "Safety Task Execution",
                    "building": building,
                    "task": task,
                    "execution_date": round_date,
                    "execution_status": execution_status,
                    "notes": line.get("notes"),
                    "evidence_photo": line.get("evidence_photo") or None,
                    "safety_round": round_doc.name,
                }
            )
            ste.insert(ignore_permissions=False)
            if ratify:
                ste.submit()
            count += 1

        if ratify:
            round_doc.submit()
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    else:
        frappe.db.release_savepoint(savepoint)

    return round_doc, count


_REPORT_ROLE = "Accommodation Manager"


@frappe.whitelist(methods=["POST"])
def submit_due_rounds(building, round_date, results):
    ratify = frappe.has_permission("Safety Task Execution", "submit")
    if not ratify:
        frappe.has_permission("Safety Task Execution", "create", throw=True)

    if not building:
        frappe.throw(_("A building is required to submit rounds."))
    validate_building_scope(doctype="Safety Round")
    frappe.has_permission("Building", "read", doc=building, throw=True)
    if not round_date:
        frappe.throw(_("A round date is required to submit rounds."))

    try:
        results = frappe.parse_json(results)
    except ValueError:
        frappe.throw(_("Results must be valid JSON."))
    if not isinstance(results, list):
        frappe.throw(_("Results must be a list."))

    by_cadence: dict[str, list] = {}
    for line in results:
        cadence = line.get("cadence")
        if not cadence:
            frappe.throw(_("Each result line needs a cadence."))
        if cadence not in _CADENCE_ORDER:
            frappe.throw(_("Unknown cadence: {0}").format(cadence))
        by_cadence.setdefault(cadence, []).append(line)

    if not by_cadence:
        frappe.throw(_("No result lines to submit."))

    rounds = []
    failed = []
    total = 0
    for cadence in _CADENCE_ORDER:
        lines = by_cadence.get(cadence)
        if not lines:
            continue
        try:
            round_doc, count = _create_round(
                building, cadence, round_date, lines, is_reinspection=0, ratify=ratify
            )
        except Exception as exc:
            failed.append({"cadence": cadence, "message": _refusal_text(exc)})
            continue
        round_doc.reload()
        rounds.append(
            {
                "cadence": cadence,
                "safety_round": round_doc.name,
                "overall_result": round_doc.overall_result,
            }
        )
        total += count

    emailed = _email_round_report(building, round_date, rounds) if rounds and ratify else False

    return {
        "ok": bool(rounds),
        "ratified": ratify,
        "rounds": rounds,
        "failed": failed,
        "count": total,
        "emailed": emailed,
    }


def _refusal_text(exc: Exception) -> str:
    log = getattr(frappe.local, "message_log", None) or []
    text = ""
    if log:
        last = log[-1]
        raw = last.get("message") if isinstance(last, dict) else last
        text = frappe.utils.strip_html(str(raw or "")).strip()
        frappe.clear_last_message()
    return text or str(exc) or _("This cadence could not be recorded.")


def _report_recipients():
    try:
        configured = frappe.db.get_single_value(
            "Habitat Settings", "safety_report_recipient"
        )
    except Exception:
        configured = None
    if configured:
        return [configured]

    users = get_users_with_role(_REPORT_ROLE)
    if not users:
        return []
    return frappe.get_all(
        "User",
        filters={"name": ["in", users], "email": ["is", "set"]},
        pluck="email",
    )


def _round_report_html(building, round_date, rounds):
    subject = _("Safety Round Report: {0} ({1})").format(building, round_date)

    sections = []
    for r in rounds:
        issues = frappe.get_all(
            "Safety Task Execution",
            filters={
                "safety_round": r["safety_round"],
                "execution_status": ["in", ["Poor", "Not Done"]],
            },
            fields=["task", "execution_status", "notes"],
            order_by="execution_status",
        )
        if issues:
            items = "".join(
                "<li>{0} &mdash; <b>{1}</b>{2}</li>".format(
                    frappe.utils.escape_html(it.task or ""),
                    frappe.utils.escape_html(_(it.execution_status) if it.execution_status else ""),
                    (": " + frappe.utils.escape_html(it.notes)) if it.notes else "",
                )
                for it in issues
            )
            issues_html = "<ul>{0}</ul>".format(items)
        else:
            issues_html = "<p>{0}</p>".format(_("No issues recorded."))

        sections.append(
            "<h4>{0} &mdash; {1}</h4>{2}".format(
                frappe.utils.escape_html(_(r["cadence"]) if r["cadence"] else ""),
                frappe.utils.escape_html(_(r.get("overall_result")) if r.get("overall_result") else ""),
                issues_html,
            )
        )

    message = "<p>{0}</p>{1}".format(
        _("Safety rounds were recorded for {0} on {1}.").format(building, round_date),
        "".join(sections),
    )
    return subject, message


def _email_round_report(building, round_date, rounds):
    if not rounds:
        return False

    if not frappe.db.get_single_value("Habitat Settings", "enable_email_notifications"):
        return False

    recipients = mailable(_report_recipients())
    if not recipients:
        return False

    try:
        subject, message = _round_report_html(building, round_date, rounds)
        frappe.sendmail(
            recipients=recipients,
            subject=subject,
            message=message,
            reference_doctype="Safety Round",
            reference_name=rounds[0]["safety_round"],
        )
        return True
    except Exception:
        frappe.log_error(
            title="Safety round report email failed",
            message=frappe.get_traceback(),
        )
        return False
