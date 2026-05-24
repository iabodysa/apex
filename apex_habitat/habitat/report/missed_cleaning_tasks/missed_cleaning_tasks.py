# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, today, add_days


def execute(filters=None):
    filters = filters or {}

    date_from = getdate(filters.get("date_from") or add_days(today(), -30))
    date_to = getdate(filters.get("date_to") or today())

    columns = [
        {"label": frappe._("Log"), "fieldname": "name", "fieldtype": "Link", "options": "Cleaning Log", "width": 140},
        {"label": frappe._("Date"), "fieldname": "cleaning_date", "fieldtype": "Date", "width": 100},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 160},
        {"label": frappe._("Cleaner Type"), "fieldname": "cleaner_type", "fieldtype": "Data", "width": 110},
        {"label": frappe._("Cleaner"), "fieldname": "cleaner", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Issue"), "fieldname": "issue", "fieldtype": "Data", "width": 130},
        {"label": frappe._("Missed Reason"), "fieldname": "missed_reason", "fieldtype": "Data", "width": 200},
        {"label": frappe._("Supervisor Approved"), "fieldname": "supervisor_approved", "fieldtype": "Check", "width": 130},
        {"label": frappe._("Scheduled Task"), "fieldname": "scheduled_task_instance", "fieldtype": "Link", "options": "Scheduled Task Instance", "width": 140},
        {"label": frappe._("Days Since"), "fieldname": "days_since", "fieldtype": "Int", "width": 90},
    ]

    query_filters = {
        "cleaning_date": ["between", [str(date_from), str(date_to)]],
        "missed_cleaning": ["in", [1, "Yes"]],
    }

    if filters.get("building"):
        query_filters["building"] = filters["building"]

    # Missed cleaning logs
    missed = frappe.get_all(
        "Cleaning Log",
        filters=query_filters,
        fields=[
            "name", "cleaning_date", "building", "cleaner_type",
            "cleaner_employee", "cleaned_by", "missed_cleaning",
            "missed_reason", "rework_required", "supervisor_approved",
            "scheduled_task_instance",
        ],
        order_by="cleaning_date desc",
    )

    # Rework-only logs (not already captured as missed)
    rework_filters = {
        "cleaning_date": ["between", [str(date_from), str(date_to)]],
        "rework_required": ["in", [1, "Yes"]],
        "missed_cleaning": ["in", [0, "No"]],
    }
    if filters.get("building"):
        rework_filters["building"] = filters["building"]

    rework = frappe.get_all(
        "Cleaning Log",
        filters=rework_filters,
        fields=[
            "name", "cleaning_date", "building", "cleaner_type",
            "cleaner_employee", "cleaned_by", "missed_cleaning",
            "missed_reason", "rework_required", "supervisor_approved",
            "scheduled_task_instance",
        ],
        order_by="cleaning_date desc",
    )

    today_date = getdate(today())

    # Prefetch employee names for all cleaner_employee values in one query
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
        cleaner_label = log.cleaned_by or ""
        if log.cleaner_employee:
            cleaner_label = employee_name_map.get(log.cleaner_employee) or log.cleaner_employee
        days = (today_date - getdate(log.cleaning_date)).days if log.cleaning_date else 0
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
        label = "Missed + Rework" if log.rework_required else "Missed"
        data.append(build_row(log, label))
    for log in rework:
        data.append(build_row(log, "Rework Required"))

    data.sort(key=lambda r: (r["building"] or "", str(r["cleaning_date"] or "")))

    return columns, data
