# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


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
        if filters.get("from_date") and filters.get("to_date"):
            attendance_filters["attendance_date"] = ["between", [filters["from_date"], filters["to_date"]]]
        elif filters.get("from_date"):
            attendance_filters["attendance_date"] = [">=", filters["from_date"]]
        elif filters.get("to_date"):
            attendance_filters["attendance_date"] = ["<=", filters["to_date"]]

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
