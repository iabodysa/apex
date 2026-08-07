# Copyright (c) 2026, AFMCO and contributors

import frappe
from frappe import _
from frappe.utils import flt

from apex.apex_core.utils.report_helpers import date_range_condition, scoped_names
from apex.salis import permissions
from apex.apex_core.utils.report_summary import count_card, percent_card, total_card


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

    or_filters = None
    restrict, allowed = permissions.report_project_scope(frappe.session.user)
    if restrict:
        in_scope_drivers = scoped_names("Salis Driver", allowed) if allowed else []
        if in_scope_drivers:
            or_filters = {"driver": ["in", in_scope_drivers], "owner": frappe.session.user}
        else:
            attendance_filters["owner"] = frappe.session.user

    records = frappe.get_all(
        "Driver Attendance",
        filters=attendance_filters,
        or_filters=or_filters,
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

    present = sum(flt(r.get("present")) for r in data)
    absent = sum(flt(r.get("absent")) for r in data)
    summary = [
        count_card(_("Drivers"), data),
        total_card(_("Present"), data, "present", "Int", indicator="Green"),
        total_card(_("Absent"), data, "absent", "Int", indicator="Red" if absent else None),
        percent_card(_("Attendance"), present, present + absent),
    ]
    return columns, data, None, None, summary
