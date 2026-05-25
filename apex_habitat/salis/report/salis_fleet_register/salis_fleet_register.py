# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {"label": frappe._("Plate"), "fieldname": "plate_normalized", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Category"), "fieldname": "vehicle_category", "fieldtype": "Link", "options": "Vehicle Category", "width": 160},
        {"label": frappe._("Ownership"), "fieldname": "ownership", "fieldtype": "Data", "width": 110},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
        {"label": frappe._("Current Driver"), "fieldname": "current_driver", "fieldtype": "Link", "options": "Salis Driver", "width": 180},
        {"label": frappe._("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 180},
    ]

    query_filters = {}
    if filters:
        for field in ("vehicle_category", "ownership", "status", "project"):
            if filters.get(field):
                query_filters[field] = filters[field]

    data = frappe.get_all(
        "Salis Vehicle",
        filters=query_filters,
        fields=[
            "plate_normalized",
            "vehicle_category",
            "ownership",
            "status",
            "current_driver",
            "project",
        ],
        order_by="plate_normalized asc",
    )

    return columns, data
