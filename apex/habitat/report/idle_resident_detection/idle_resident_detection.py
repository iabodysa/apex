# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

"""Idle Resident Detection — housed workers whose work has ended.

Auto-detection layer the Idle Resident Report DocType lacked: an Idle Resident
Report only existed once someone created it by hand, so a forgotten resident went
unseen. This report derives the candidates from the records — an active
Accommodation Assignment (the canonical active-stay definition: submitted, no
check-out date) whose linked Project is Completed/Cancelled, or which has no
Project link at all — and shows whether an Idle Resident Report has already been
opened, so a manager triages the undetected ones rather than re-logging known
ones.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, today

from apex.habitat import permissions

# [#kbzrzp]
ENDED_PROJECT_STATUSES = ("Completed", "Cancelled")
# [#d3ahsh]
OPEN_REPORT_STATUSES = ("Open", "Acknowledged")


def execute(filters=None):
    filters = filters or {}
    columns = _columns()
    data = _get_data(filters)
    return columns, data


def _columns():
    return [
        {"label": _("Assignment"), "fieldname": "name", "fieldtype": "Link", "options": "Housing Assignment", "width": 150},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 150},
        {"label": _("Room"), "fieldname": "room", "fieldtype": "Link", "options": "Room", "width": 110},
        {"label": _("Bed"), "fieldname": "bed", "fieldtype": "Link", "options": "Bed", "width": 110},
        {"label": _("Check-in Date"), "fieldname": "check_in_date", "fieldtype": "Date", "width": 110},
        {"label": _("Days Housed"), "fieldname": "days_housed", "fieldtype": "Int", "width": 100},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 140},
        {"label": _("Project Status"), "fieldname": "project_status", "fieldtype": "Data", "width": 110},
        {"label": _("Idle Report"), "fieldname": "existing_idle_report", "fieldtype": "Link", "options": "Idle Resident Report", "width": 150},
        {"label": _("Idle Report Status"), "fieldname": "idle_report_status", "fieldtype": "Data", "width": 130},
    ]


def _get_data(filters):
    query_filters = {"docstatus": 1, "check_out_date": ["is", "not set"]}

    # [#cxlwka]
    user = frappe.session.user
    if not permissions._building_is_unscoped(user):
        allowed = permissions._allowed_buildings(user)
        if filters.get("building"):
            allowed = [b for b in allowed if b == filters["building"]]
        if not allowed:
            return []
        query_filters["building"] = ["in", allowed]
    elif filters.get("building"):
        query_filters["building"] = filters["building"]

    assignments = frappe.get_all(
        "Housing Assignment",
        filters=query_filters,
        fields=[
            "name", "employee", "employee_name", "building", "room", "bed",
            "check_in_date", "project",
        ],
        order_by="building asc, check_in_date asc",
    )
    if not assignments:
        return []

    project_status = _project_status_map(assignments)
    reports = _open_idle_reports_by_assignment()
    only_unlogged = bool(filters.get("only_unlogged"))
    wanted_status = filters.get("project_status")

    today_str = today()
    data = []
    for asg in assignments:
        status = project_status.get(asg.project) if asg.project else None
        # [#3909gv]
        if asg.project and status not in ENDED_PROJECT_STATUSES:
            continue
        if wanted_status and (status or "") != wanted_status:
            continue

        report = reports.get(asg.name)
        if only_unlogged and report:
            continue

        data.append({
            "name": asg.name,
            "employee": asg.employee,
            "employee_name": asg.employee_name,
            "building": asg.building,
            "room": asg.room,
            "bed": asg.bed,
            "check_in_date": asg.check_in_date,
            "days_housed": date_diff(today_str, asg.check_in_date) if asg.check_in_date else None,
            "project": asg.project,
            "project_status": status or _("No Project"),
            "existing_idle_report": report.get("name") if report else None,
            "idle_report_status": report.get("status") if report else None,
        })
    return data


def _project_status_map(assignments):
    """One read for the status of every distinct linked project."""
    project_names = list({a.project for a in assignments if a.project})
    if not project_names:
        return {}
    rows = frappe.get_all(
        "Project",
        filters={"name": ["in", project_names]},
        fields=["name", "status"],
    )
    return {r.name: r.status for r in rows}


def _open_idle_reports_by_assignment():
    """Most-recent open/acknowledged Idle Resident Report per assignment, so each
    candidate shows whether it is already logged. Ordered ascending so the last
    write wins and the newest report is kept."""
    rows = frappe.get_all(
        "Idle Resident Report",
        filters={"status": ["in", OPEN_REPORT_STATUSES], "assignment": ["is", "set"]},
        fields=["name", "assignment", "status"],
        order_by="creation asc",
    )
    by_assignment = {}
    for r in rows:
        by_assignment[r.assignment] = {"name": r.name, "status": r.status}
    return by_assignment
