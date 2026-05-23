# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, today


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": frappe._("Execution"), "fieldname": "name", "fieldtype": "Link", "options": "Safety Task Execution", "width": 150},
        {"label": frappe._("Execution Date"), "fieldname": "execution_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 160},
        {"label": frappe._("Task"), "fieldname": "task", "fieldtype": "Link", "options": "Safety Task Catalog", "width": 200},
        {"label": frappe._("Priority"), "fieldname": "priority", "fieldtype": "Data", "width": 90},
        {"label": frappe._("Result"), "fieldname": "execution_status", "fieldtype": "Data", "width": 120},
        {"label": frappe._("Executed By"), "fieldname": "executed_by", "fieldtype": "Link", "options": "User", "width": 140},
        {"label": frappe._("Linked Maintenance"), "fieldname": "linked_maintenance_request", "fieldtype": "Link", "options": "Maintenance Request", "width": 150},
        {"label": frappe._("Days Open"), "fieldname": "days_open", "fieldtype": "Int", "width": 90},
    ]

    query_filters = {"docstatus": 1, "execution_status": ["in", ["Failed", "Partially Completed", "Escalated"]]}
    if filters.get("building"):
        query_filters["building"] = filters["building"]
    if filters.get("priority"):
        query_filters["priority"] = filters["priority"]

    rows = frappe.get_all(
        "Safety Task Execution",
        filters=query_filters,
        fields=[
            "name", "execution_date", "building", "task", "priority",
            "execution_status", "executed_by", "linked_maintenance_request",
        ],
        order_by="priority desc, execution_date asc",
    )

    data = []
    for row in rows:
        days_open = (getdate(today()) - getdate(row.execution_date)).days if row.execution_date else 0
        data.append({
            "name": row.name,
            "execution_date": row.execution_date,
            "building": row.building,
            "task": row.task,
            "priority": row.priority or "",
            "execution_status": row.execution_status,
            "executed_by": row.executed_by,
            "linked_maintenance_request": row.linked_maintenance_request or "",
            "days_open": days_open,
        })

    return columns, data
