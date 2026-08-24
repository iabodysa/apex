# Copyright (c) 2026, afmcoltd


import frappe
from frappe import _
from frappe.utils import add_days, date_diff, getdate, today

from apex.habitat import permissions
from apex.apex_core.utils.report_summary import count_card


def execute(filters=None):
    filters = filters or {}

    date_from = getdate(filters.get("date_from") or add_days(today(), -30))
    date_to = getdate(filters.get("date_to") or today())

    columns = [
        {"label": frappe._("Log"), "fieldname": "name", "fieldtype": "Link", "options": "Cleaning Log", "width": 140},
        {"label": frappe._("Date"), "fieldname": "cleaning_date", "fieldtype": "Date", "width": 100},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 160},
        {"label": frappe._("Cleaner Type"), "fieldname": "cleaner_type", "fieldtype": "Data", "width": 110},
        {"label": frappe._("Cleaner"), "fieldname": "cleaner", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Issue"), "fieldname": "issue", "fieldtype": "Data", "width": 130},
        {"label": frappe._("Missed Reason"), "fieldname": "missed_reason", "fieldtype": "Data", "width": 200},
        {"label": frappe._("Supervisor Approved"), "fieldname": "supervisor_approved", "fieldtype": "Check", "width": 130},
        {"label": frappe._("Scheduled Task"), "fieldname": "scheduled_task_instance", "fieldtype": "Link", "options": "Scheduled Task Instance", "width": 140},
        {"label": frappe._("Days Since"), "fieldname": "days_since", "fieldtype": "Int", "width": 90},
    ]

    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Cleaning Log")
    chosen = filters.get("building")
    if restrict:
        if not allowed or (chosen and chosen not in allowed):
            return columns, []

    def apply_building_scope(qf):
        if chosen:
            qf["building"] = chosen
        elif restrict:
            qf["building"] = ["in", allowed]
        return qf

    query_filters = apply_building_scope({
        "cleaning_date": ["between", [str(date_from), str(date_to)]],
        "missed_cleaning": ["in", [1, "Yes"]],
        "docstatus": ["!=", 2],
    })

    missed = frappe.get_all(
        "Cleaning Log",
        filters=query_filters,
        fields=[
            "name", "cleaning_date", "building", "cleaner_type",
            "cleaner_employee", "cleaner_name", "missed_cleaning",
            "missed_reason", "rework_required", "supervisor_approved",
            "scheduled_task_instance",
        ],
        order_by="cleaning_date desc",
    )

    rework_filters = apply_building_scope({
        "cleaning_date": ["between", [str(date_from), str(date_to)]],
        "rework_required": ["in", [1, "Yes"]],
        "missed_cleaning": ["in", [0, "No"]],
        "docstatus": ["!=", 2],
    })

    rework = frappe.get_all(
        "Cleaning Log",
        filters=rework_filters,
        fields=[
            "name", "cleaning_date", "building", "cleaner_type",
            "cleaner_employee", "cleaner_name", "missed_cleaning",
            "missed_reason", "rework_required", "supervisor_approved",
            "scheduled_task_instance",
        ],
        order_by="cleaning_date desc",
    )

    today_str = today()

    all_logs = list(missed) + list(rework)
    all_cleaner_employees = list({log.cleaner_employee for log in all_logs if log.cleaner_employee})
    employee_name_map = {}
    if all_cleaner_employees:
        emp_rows = frappe.get_all(
            "Employee",
            filters={"name": ["in", all_cleaner_employees]},
            fields=["name", "employee_name"],
        )
        employee_name_map = {e.name: e.employee_name for e in emp_rows}

    def build_row(log, issue_label):
        cleaner_label = log.cleaner_name or ""
        if log.cleaner_employee:
            cleaner_label = employee_name_map.get(log.cleaner_employee) or log.cleaner_employee
        days = date_diff(today_str, log.cleaning_date) if log.cleaning_date else 0
        return {
            "name": log.name,
            "cleaning_date": log.cleaning_date,
            "building": log.building,
            "cleaner_type": log.cleaner_type or "",
            "cleaner": cleaner_label,
            "issue": issue_label,
            "missed_reason": log.missed_reason or "",
            "supervisor_approved": log.supervisor_approved,
            "scheduled_task_instance": log.scheduled_task_instance or "",
            "days_since": days,
        }

    data = []
    for log in missed:
        label = frappe._("Missed + Rework") if log.rework_required else frappe._("Missed")
        data.append(build_row(log, label))
    for log in rework:
        data.append(build_row(log, frappe._("Rework Required")))

    data.sort(key=lambda r: (r["building"] or "", str(r["cleaning_date"] or "")))

    summary = [
        count_card(_("Missed Tasks"), data),
        count_card(_("Missed Over 7 Days"), data, lambda r: (r.get("days_since") or 0) > 7, "Red"),
    ]
    return columns, data, None, None, summary
