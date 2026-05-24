# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, today, add_days


def execute(filters=None):
    filters = filters or {}

    date_from = getdate(filters.get("date_from") or add_days(today(), -7))
    date_to = getdate(filters.get("date_to") or today())

    columns = [
        {"label": frappe._("Log"), "fieldname": "name", "fieldtype": "Link", "options": "Cleaning Log", "width": 140},
        {"label": frappe._("Date"), "fieldname": "cleaning_date", "fieldtype": "Date", "width": 100},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 160},
        {"label": frappe._("Cleaner Type"), "fieldname": "cleaner_type", "fieldtype": "Data", "width": 110},
        {"label": frappe._("Cleaner"), "fieldname": "cleaner", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Rooms Total"), "fieldname": "rooms_total", "fieldtype": "Int", "width": 90},
        {"label": frappe._("Rooms Cleaned"), "fieldname": "rooms_cleaned", "fieldtype": "Int", "width": 100},
        {"label": frappe._("Compliance %"), "fieldname": "compliance_pct", "fieldtype": "Float", "precision": 1, "width": 100},
        {"label": frappe._("Supervisor Approved"), "fieldname": "supervisor_approved", "fieldtype": "Check", "width": 130},
        {"label": frappe._("Rating"), "fieldname": "supervisor_rating", "fieldtype": "Data", "width": 90},
        {"label": frappe._("Missed"), "fieldname": "missed_cleaning", "fieldtype": "Check", "width": 70},
        {"label": frappe._("Rework Required"), "fieldname": "rework_required", "fieldtype": "Check", "width": 110},
        {"label": frappe._("Missed Reason"), "fieldname": "missed_reason", "fieldtype": "Data", "width": 180},
        {"label": frappe._("Scheduled Task"), "fieldname": "scheduled_task_instance", "fieldtype": "Link", "options": "Scheduled Task Instance", "width": 140},
    ]

    query_filters = {
        "cleaning_date": ["between", [str(date_from), str(date_to)]],
    }
    if filters.get("building"):
        query_filters["building"] = filters["building"]
    if filters.get("missed_only"):
        query_filters["missed_cleaning"] = 1

    logs = frappe.get_all(
        "Cleaning Log",
        filters=query_filters,
        fields=[
            "name", "cleaning_date", "building", "cleaner_type",
            "cleaner_employee", "cleaned_by", "supervisor_approved",
            "supervisor_rating", "missed_cleaning", "missed_reason",
            "rework_required", "scheduled_task_instance",
        ],
        order_by="cleaning_date desc, building asc",
    )

    # Fetch room detail counts in bulk
    all_log_names = [log.name for log in logs]
    room_rows = []
    if all_log_names:
        room_rows = frappe.get_all(
            "Cleaning Log Room Detail",
            filters={"parent": ["in", all_log_names], "parenttype": "Cleaning Log"},
            fields=["parent", "cleaned"],
        )

    from collections import defaultdict
    room_totals = defaultdict(int)
    room_cleaned = defaultdict(int)
    for rr in room_rows:
        room_totals[rr.parent] += 1
        if rr.cleaned:
            room_cleaned[rr.parent] += 1

    # Prefetch employee names for all cleaner_employee values in one query
    all_cleaner_employees = list({log.cleaner_employee for log in logs if log.cleaner_employee})
    employee_name_map = {}
    if all_cleaner_employees:
        emp_rows = frappe.get_all(
            "Employee",
            filters={"name": ["in", all_cleaner_employees]},
            fields=["name", "employee_name"],
        )
        employee_name_map = {e.name: e.employee_name for e in emp_rows}

    data = []
    for log in logs:
        total = room_totals[log.name]
        cleaned = room_cleaned[log.name]
        pct = (cleaned / total * 100) if total else (0.0 if log.missed_cleaning else 100.0)

        cleaner_label = log.cleaned_by or ""
        if log.cleaner_employee:
            cleaner_label = employee_name_map.get(log.cleaner_employee) or log.cleaner_employee

        data.append({
            "name": log.name,
            "cleaning_date": log.cleaning_date,
            "building": log.building,
            "cleaner_type": log.cleaner_type or "",
            "cleaner": cleaner_label,
            "rooms_total": total,
            "rooms_cleaned": cleaned,
            "compliance_pct": round(pct, 1),
            "supervisor_approved": log.supervisor_approved,
            "supervisor_rating": log.supervisor_rating or "",
            "missed_cleaning": log.missed_cleaning,
            "rework_required": log.rework_required,
            "missed_reason": log.missed_reason or "",
            "scheduled_task_instance": log.scheduled_task_instance or "",
        })

    return columns, data
