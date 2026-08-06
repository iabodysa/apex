# Copyright (c) 2026, AFMCO and contributors

import frappe

from apex.apex_core.utils.report_helpers import date_range_condition, scoped_names
from apex.salis import permissions


def execute(filters=None):
    columns = [
        {"label": frappe._("Scanned At"), "fieldname": "scanned_at", "fieldtype": "Datetime", "width": 165},
        {"label": frappe._("Result"), "fieldname": "result", "fieldtype": "Data", "width": 120},
        {"label": frappe._("Method"), "fieldname": "method", "fieldtype": "Data", "width": 90},
        {"label": frappe._("Driver"), "fieldname": "driver", "fieldtype": "Link", "options": "Salis Driver", "width": 160},
        {"label": frappe._("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 160},
        {"label": frappe._("Trip"), "fieldname": "dispatch_trip", "fieldtype": "Link", "options": "Dispatch Trip", "width": 150},
        {"label": frappe._("Building"), "fieldname": "accommodation_building", "fieldtype": "Link", "options": "Building", "width": 150},
        {"label": frappe._("Boarding Event Created"), "fieldname": "boarding_event_created", "fieldtype": "Check", "width": 170},
        {"label": frappe._("Notes"), "fieldname": "notes", "fieldtype": "Small Text", "width": 220},
    ]

    scan_filters = {}
    if filters:
        date_condition = date_range_condition(filters, "scanned_at")
        if date_condition is not None:
            scan_filters["scanned_at"] = date_condition
        if filters.get("result"):
            scan_filters["result"] = filters["result"]

    restrict, allowed = permissions.report_project_scope(frappe.session.user)
    if restrict:
        in_scope_drivers = scoped_names("Salis Driver", allowed) if allowed else []
        if not in_scope_drivers:
            return columns, []
        scan_filters["driver"] = ["in", in_scope_drivers]

    rows = frappe.get_all(
        "Boarding Scan Log",
        filters=scan_filters,
        fields=[
            "scanned_at",
            "result",
            "method",
            "driver",
            "employee",
            "dispatch_trip",
            "accommodation_building",
            "boarding_event_created",
            "notes",
        ],
        order_by="scanned_at desc",
        limit_page_length=0,
    )
    return columns, rows
