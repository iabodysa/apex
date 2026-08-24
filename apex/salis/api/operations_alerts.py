# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.desk.form import assign_to
from frappe.utils import add_to_date, get_datetime, now_datetime

from apex.apex_core.utils.role_assignment import clear_assignment
from apex.salis.api.assignment_queue import open_queue_rows, queue_ref
from apex.salis.api.dispatch_board import _permitted_projects
from apex.salis.api.enrich import vehicle_driver_titles
from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int
from apex.salis.tasks import QUEUE_DOCTYPES

SEVERITIES = ["Info", "Warning", "Critical"]

AGING_SETTING = {"Critical": "alert_aging_critical_hours", "Warning": "alert_aging_warning_hours", "Info": "alert_aging_info_hours"}
AGING_DEFAULT = {"Critical": 4, "Warning": 24, "Info": 72}


def _aging_thresholds() -> dict:
    return {sev: get_salis_int(AGING_SETTING[sev], AGING_DEFAULT[sev]) for sev in SEVERITIES}


def _scoped_vehicles(unscoped, projects):
    if unscoped:
        return None
    if not projects:
        return []
    return frappe.get_all(
        "Salis Vehicle",
        filters={"project": ["in", projects]},
        pluck="name",
        limit_page_length=0,
    )


@frappe.whitelist()
def get_open_alerts(project=None, severity=None, since=None):
    frappe.has_permission("Salis Vehicle", "read", throw=True)
    unscoped, projects = _permitted_projects()

    proj_opts = (
        [p.name for p in frappe.get_list("Project", fields=["name"], order_by="name asc", limit_page_length=0)]
        if unscoped
        else list(projects or [])
    )

    now = now_datetime()

    if project and (unscoped or project in (projects or [])):
        plates = frappe.get_list(
            "Salis Vehicle", filters={"project": project}, pluck="name", limit_page_length=0
        )
    else:
        plates = _scoped_vehicles(unscoped, projects)

    alerts = open_queue_rows()
    if severity in SEVERITIES:
        alerts = [r for r in alerts if r.severity == severity]
    if plates is not None:
        allowed_plates = {p for p in plates if p}
        alerts = [r for r in alerts if r.vehicle and r.vehicle in allowed_plates]
    alerts.sort(key=lambda a: str(a.get("raised_on") or ""), reverse=True)

    vehicle_driver_titles(alerts)

    for a in alerts:
        a["assignees"] = frappe.parse_json(a.get("_assign")) or []
    user = frappe.session.user
    assignee_ids = list({u for a in alerts for u in a["assignees"]})
    name_map = {
        u.name: u.full_name
        for u in frappe.get_list(
            "User", filters={"name": ["in", assignee_ids]}, fields=["name", "full_name"],
            limit_page_length=0,
        )
    } if assignee_ids else {}

    summary = {"total": len(alerts), "by_severity": {s: 0 for s in SEVERITIES}, "mine": 0, "unowned": 0}
    for a in alerts:
        a["assignee_names"] = [name_map.get(u, u) for u in a["assignees"]]
        a["snooze_until"] = None
        if a.severity in summary["by_severity"]:
            summary["by_severity"][a.severity] += 1
        if user in a["assignees"]:
            summary["mine"] += 1
        if not a["assignees"]:
            summary["unowned"] += 1

    return {
        "alerts": alerts,
        "summary": summary,
        "projects": proj_opts,
        "severities": SEVERITIES,
        "unscoped": unscoped,
        "aging_hours": _aging_thresholds(),
        "server_now": str(now),
        "current_user": user,
        "resolved_since": _resolved_since(since, plates),
    }


def _resolved_since(since, plates) -> int:
    if not since or plates is not None:
        return 0
    return frappe.db.count(
        "ToDo",
        {
            "reference_type": ["in", list(QUEUE_DOCTYPES)],
            "status": "Closed",
            "modified": [">", since],
        },
    )


def _queue_ref_checked(name):
    ref = queue_ref(name)
    if not ref:
        frappe.throw(_("Queue row {0} not found (it may have already drained).").format(name))
    frappe.has_permission(ref.reference_type, "write", doc=ref.reference_name, throw=True)
    return ref


@frappe.whitelist(methods=["POST"])
def acknowledge_alert(name):
    _queue_ref_checked(name)
    return {"ok": True, "name": name, "status": "Open", "acknowledged": False}


@frappe.whitelist(methods=["POST"])
def bulk_acknowledge_alerts(names):
    if isinstance(names, str):
        names = frappe.parse_json(names)
    acknowledged = []
    for name in names or []:
        try:
            if acknowledge_alert(name).get("ok"):
                acknowledged.append(name)
        except frappe.PermissionError:
            continue
    return {"ok": True, "acknowledged": acknowledged}


@frappe.whitelist(methods=["POST"])
def assign_alert(name, user=None):
    target = user or frappe.session.user
    ref = _queue_ref_checked(name)
    assign_to.add({
        "assign_to": [target],
        "doctype": ref.reference_type,
        "name": ref.reference_name,
    })
    assignees = frappe.get_list(
        "ToDo",
        filters={
            "reference_type": ref.reference_type,
            "reference_name": ref.reference_name,
            "status": ["in", ["Open", "Overdue"]],
        },
        pluck="allocated_to",
        distinct=True,
        limit_page_length=0,
    )
    return {"ok": True, "name": name, "assignees": assignees}


@frappe.whitelist(methods=["POST"])
def unassign_alert(name, user=None):
    target = user or frappe.session.user
    ref = _queue_ref_checked(name)
    assign_to.remove(ref.reference_type, ref.reference_name, target)
    assignees = frappe.get_list(
        "ToDo",
        filters={
            "reference_type": ref.reference_type,
            "reference_name": ref.reference_name,
            "status": ["in", ["Open", "Overdue"]],
        },
        pluck="allocated_to",
        distinct=True,
        limit_page_length=0,
    )
    return {"ok": True, "name": name, "assignees": assignees}


@frappe.whitelist(methods=["POST"])
def bulk_assign_alerts(names, user=None):
    if isinstance(names, str):
        names = frappe.parse_json(names)
    assigned = []
    for name in names or []:
        try:
            if assign_alert(name, user=user).get("ok"):
                assigned.append(name)
        except frappe.PermissionError:
            continue
    return {"ok": True, "assigned": assigned}


SNOOZE_PRESETS = {"tomorrow": ("days", 1), "2d": ("days", 2), "1w": ("days", 7)}


def _snooze_target(preset=None, until=None):
    if until:
        return get_datetime(until)
    if preset in SNOOZE_PRESETS:
        unit, amount = SNOOZE_PRESETS[preset]
        return add_to_date(now_datetime(), **{unit: amount})
    return None


@frappe.whitelist(methods=["POST"])
def snooze_alert(name, preset=None, until=None):
    _queue_ref_checked(name)
    _snooze_target(preset, until)
    return {"ok": True, "name": name, "snooze_until": None}


@frappe.whitelist(methods=["POST"])
def bulk_snooze_alerts(names, preset=None, until=None):
    if isinstance(names, str):
        names = frappe.parse_json(names)
    snoozed = []
    for name in names or []:
        try:
            if snooze_alert(name, preset=preset, until=until).get("ok"):
                snoozed.append(name)
        except frappe.PermissionError:
            continue
    return {"ok": True, "snoozed": snoozed}


@frappe.whitelist(methods=["POST"])
def resolve_alert(name, note=None):
    reason = (note or _("Resolved by {0}").format(frappe.session.user)).strip()
    ref = _queue_ref_checked(name)
    resolved = bool(clear_assignment(ref.reference_type, ref.reference_name))
    try:
        frappe.get_doc(ref.reference_type, ref.reference_name).add_comment(
            "Info", _("Queue resolved: {0}").format(reason)
        )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Queue resolve comment failed for {ref.reference_name}"[:140],
        )
    return {"ok": True, "name": name, "status": "Resolved", "resolved": resolved}
