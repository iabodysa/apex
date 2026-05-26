# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": frappe._("Request"), "fieldname": "name", "fieldtype": "Link", "options": "Transport Request", "width": 160},
        {"label": frappe._("Request Type"), "fieldname": "request_type", "fieldtype": "Data", "width": 200},
        {"label": frappe._("Accommodation Building"), "fieldname": "accommodation_building", "fieldtype": "Link", "options": "Accommodation Building", "width": 180},
        {"label": frappe._("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 180},
        {"label": frappe._("Workers"), "fieldname": "worker_count", "fieldtype": "Int", "width": 90},
        {"label": frappe._("Cross Region"), "fieldname": "is_cross_region", "fieldtype": "Check", "width": 110},
        {"label": frappe._("Pickup"), "fieldname": "pickup_datetime", "fieldtype": "Datetime", "width": 160},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
        {"label": frappe._("Vehicle"), "fieldname": "assigned_vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 160},
        {"label": frappe._("Driver"), "fieldname": "assigned_driver", "fieldtype": "Link", "options": "Salis Driver", "width": 160},
    ]

    query_filters = {"service_line": "Workers"}

    for field in ("request_type", "status"):
        if filters.get(field):
            query_filters[field] = filters[field]

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if from_date and to_date:
        query_filters["pickup_datetime"] = ["between", [from_date, to_date]]
    elif from_date:
        query_filters["pickup_datetime"] = [">=", from_date]
    elif to_date:
        query_filters["pickup_datetime"] = ["<=", to_date]

    data = frappe.get_all(
        "Transport Request",
        filters=query_filters,
        fields=[
            "name",
            "request_type",
            "accommodation_building",
            "project",
            "worker_count",
            "is_cross_region",
            "pickup_datetime",
            "status",
            "assigned_vehicle",
            "assigned_driver",
        ],
        order_by="pickup_datetime asc",
    )

    return columns, data
