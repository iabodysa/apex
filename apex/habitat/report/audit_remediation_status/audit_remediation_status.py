# Copyright (c) 2026, AFMCO and contributors

import frappe
from frappe.utils import getdate, today

from apex.habitat import permissions


def execute(filters=None):
    columns = [
        {"label": frappe._("Remediation Plan"), "fieldname": "plan", "fieldtype": "Link", "options": "Audit Remediation Plan", "width": 150},
        {"label": frappe._("Remediation Action"), "fieldname": "remediation_action", "fieldtype": "Small Text", "width": 260},
        {"label": frappe._("Owner Role"), "fieldname": "owner_role", "fieldtype": "Link", "options": "Role", "width": 140},
        {"label": frappe._("Owner User"), "fieldname": "owner_user", "fieldtype": "Link", "options": "User", "width": 160},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 110},
        {"label": frappe._("Completion Date"), "fieldname": "completion_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Overdue"), "fieldname": "overdue", "fieldtype": "Data", "width": 90},
    ]

    item_filters = {"parenttype": "Audit Remediation Plan"}
    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    if restrict:
        if not allowed:
            return columns, []
        plans = frappe.get_all(
            "Audit Remediation Building Scope",
            filters={
                "parenttype": "Audit Remediation Plan",
                "building": ["in", allowed],
            },
            pluck="parent",
        )
        if not plans:
            return columns, []
        item_filters["parent"] = ["in", sorted(set(plans))]

    rows = frappe.get_all(
        "Audit Remediation Item",
        filters=item_filters,
        fields=[
            "parent as plan",
            "remediation_action",
            "owner_role",
            "owner_user",
            "status",
            "due_date",
            "completion_date",
        ],
        order_by="due_date asc",
    )

    today_date = getdate(today())
    closed_states = ("Verified by Client",)
    data = []
    for row in rows:
        is_overdue = bool(
            row.get("due_date")
            and not row.get("completion_date")
            and getdate(row["due_date"]) < today_date
            and row.get("status") not in closed_states
        )
        row["overdue"] = "Yes" if is_overdue else "No"
        data.append(row)
    return columns, data
