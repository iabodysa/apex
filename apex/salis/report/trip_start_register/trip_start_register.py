# Copyright (c) 2026, AFMCO and contributors

import frappe
from frappe import _
from frappe.utils import flt

from apex.apex_core.utils.report_helpers import date_range_condition, scoped_names
from apex.salis import permissions
from apex.apex_core.utils.report_summary import count_card, percent_card, total_card


def execute(filters=None):
    columns = [
        {"label": frappe._("Trip Date"), "fieldname": "trip_date", "fieldtype": "Date", "width": 110},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": frappe._("Trip"), "fieldname": "dispatch_trip", "fieldtype": "Link", "options": "Dispatch Trip", "width": 150},
        {"label": frappe._("Driver"), "fieldname": "driver", "fieldtype": "Link", "options": "Salis Driver", "width": 160},
        {"label": frappe._("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 140},
        {"label": frappe._("Route Plan"), "fieldname": "route_plan", "fieldtype": "Link", "options": "Route Plan", "width": 150},
        {"label": frappe._("Started"), "fieldname": "start_datetime", "fieldtype": "Datetime", "width": 165},
        {"label": frappe._("Ended"), "fieldname": "end_datetime", "fieldtype": "Datetime", "width": 165},
        {"label": frappe._("Expected"), "fieldname": "expected_count", "fieldtype": "Int", "width": 100},
        {"label": frappe._("Boarded"), "fieldname": "boarded_count", "fieldtype": "Int", "width": 100},
        {"label": frappe._("Missing"), "fieldname": "missing_count", "fieldtype": "Int", "width": 100},
    ]

    log_filters = {"docstatus": ["<", 2]}
    if filters:
        date_condition = date_range_condition(filters, "trip_date")
        if date_condition is not None:
            log_filters["trip_date"] = date_condition
        if filters.get("status"):
            log_filters["status"] = filters["status"]

    restrict, allowed = permissions.report_project_scope(frappe.session.user)
    if restrict:
        in_scope_drivers = scoped_names("Salis Driver", allowed) if allowed else []
        if not in_scope_drivers:
            return columns, []
        log_filters["driver"] = ["in", in_scope_drivers]

    rows = frappe.get_all(
        "Trip Start Log",
        filters=log_filters,
        fields=[
            "trip_date",
            "status",
            "dispatch_trip",
            "driver",
            "vehicle",
            "route_plan",
            "start_datetime",
            "end_datetime",
            "expected_count",
            "boarded_count",
        ],
        order_by="trip_date desc, start_datetime desc",
        limit_page_length=0,
    )
    for row in rows:
        row["missing_count"] = max((row.get("expected_count") or 0) - (row.get("boarded_count") or 0), 0)
    expected = sum(flt(r.get("expected_count")) for r in rows)
    boarded = sum(flt(r.get("boarded_count")) for r in rows)
    summary = [
        count_card(_("Trips"), rows),
        total_card(_("Expected"), rows, "expected_count", "Int"),
        total_card(_("Missing"), rows, "missing_count", "Int", indicator="Red"),
        percent_card(_("Boarded"), boarded, expected),
    ]
    return columns, rows, None, None, summary
