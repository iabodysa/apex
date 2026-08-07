# Copyright (c) 2026, AFMCO and contributors

import frappe
from frappe import _
from frappe.utils import date_diff, today

from apex.habitat import permissions
from apex.apex_core.utils.report_summary import count_card


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": frappe._("Execution"), "fieldname": "name", "fieldtype": "Link", "options": "Safety Task Execution", "width": 150},
        {"label": frappe._("Execution Date"), "fieldname": "execution_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 160},
        {"label": frappe._("Task"), "fieldname": "task", "fieldtype": "Link", "options": "Safety Task Catalog", "width": 200},
        {"label": frappe._("Priority"), "fieldname": "priority", "fieldtype": "Data", "width": 90},
        {"label": frappe._("Result"), "fieldname": "execution_status", "fieldtype": "Data", "width": 120},
        {"label": frappe._("Executed By"), "fieldname": "executed_by", "fieldtype": "Link", "options": "User", "width": 140},
        {"label": frappe._("Linked Maintenance"), "fieldname": "linked_maintenance_request", "fieldtype": "Link", "options": "Maintenance Request", "width": 150},
        {"label": frappe._("Days Open"), "fieldname": "days_open", "fieldtype": "Int", "width": 90},
    ]

    query_filters = {"docstatus": 1, "execution_status": ["in", ["Poor", "Not Done"]]}
    if filters.get("building"):
        query_filters["building"] = filters["building"]
    if filters.get("priority"):
        query_filters["priority"] = filters["priority"]

    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    if restrict:
        chosen = query_filters.get("building")
        if not allowed or (chosen and chosen not in allowed):
            return columns, []
        if not chosen:
            query_filters["building"] = ["in", allowed]

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
        days_open = date_diff(today(), row.execution_date) if row.execution_date else 0
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

    summary = [
        count_card(_("Open Findings"), data),
        count_card(_("Open Over 30 Days"), data, lambda r: (r.get("days_open") or 0) > 30, "Red"),
        count_card(_("Open Over 7 Days"), data, lambda r: (r.get("days_open") or 0) > 7, "Orange"),
    ]
    return columns, data, None, None, summary
