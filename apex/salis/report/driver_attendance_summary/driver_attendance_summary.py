# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

import frappe

from apex.apex_core.utils.report_helpers import date_range_condition, scoped_names
from apex.salis import permissions


def execute(filters=None):
    columns = [
        {"label": frappe._("Driver"), "fieldname": "driver", "fieldtype": "Link", "options": "Salis Driver", "width": 200},
        {"label": frappe._("Present"), "fieldname": "present", "fieldtype": "Int", "width": 110},
        {"label": frappe._("Absent"), "fieldname": "absent", "fieldtype": "Int", "width": 110},
        {"label": frappe._("Late"), "fieldname": "late", "fieldtype": "Int", "width": 110},
        {"label": frappe._("Worked Hours"), "fieldname": "worked_hours", "fieldtype": "Float", "width": 140},
    ]

    attendance_filters = {}
    if filters:
        date_condition = date_range_condition(filters, "attendance_date")
        if date_condition is not None:
            attendance_filters["attendance_date"] = date_condition

    # [#qc3e9v]
    restrict, allowed = permissions.report_project_scope(frappe.session.user)
    if restrict:
        if not allowed:
            return columns, []
        in_scope_drivers = scoped_names("Salis Driver", allowed)
        if not in_scope_drivers:
            return columns, []
        attendance_filters["driver"] = ["in", in_scope_drivers]

    records = frappe.get_all(
        "Driver Attendance",
        filters=attendance_filters,
        fields=["driver", "status", "worked_hours"],
    )

    summary = {}
    for record in records:
        driver = record.driver or ""
        row = summary.setdefault(driver, {"driver": driver, "present": 0, "absent": 0, "late": 0, "worked_hours": 0.0})
        if record.status == "Present":
            row["present"] += 1
        elif record.status == "Absent":
            row["absent"] += 1
        elif record.status == "Late":
            row["late"] += 1
        row["worked_hours"] += record.worked_hours or 0

    data = sorted(summary.values(), key=lambda row: row["driver"])

    return columns, data
