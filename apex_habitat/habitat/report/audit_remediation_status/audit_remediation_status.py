# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, today


def execute(filters=None):
    columns = [
        {"label": frappe._("Remediation Plan"), "fieldname": "plan", "fieldtype": "Link", "options": "Client Audit Remediation Plan", "width": 150},
        {"label": frappe._("Remediation Action"), "fieldname": "remediation_action", "fieldtype": "Small Text", "width": 260},
        {"label": frappe._("Owner Role"), "fieldname": "owner_role", "fieldtype": "Link", "options": "Role", "width": 140},
        {"label": frappe._("Owner User"), "fieldname": "owner_user", "fieldtype": "Link", "options": "User", "width": 160},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 110},
        {"label": frappe._("Completion Date"), "fieldname": "completion_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Overdue"), "fieldname": "overdue", "fieldtype": "Data", "width": 90},
    ]

    rows = frappe.get_all(
        "Audit Remediation Item",
        filters={"parenttype": "Client Audit Remediation Plan"},
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
