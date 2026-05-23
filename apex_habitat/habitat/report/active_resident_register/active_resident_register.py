# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": frappe._("Assignment"), "fieldname": "name", "fieldtype": "Link", "options": "Accommodation Assignment", "width": 150},
        {"label": frappe._("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": frappe._("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 150},
        {"label": frappe._("Room"), "fieldname": "room", "fieldtype": "Link", "options": "Accommodation Room", "width": 120},
        {"label": frappe._("Bed"), "fieldname": "bed", "fieldtype": "Link", "options": "Accommodation Bed", "width": 120},
        {"label": frappe._("Check-in Date"), "fieldname": "check_in_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 140},
        {"label": frappe._("Cost Center"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 140},
    ]

    query_filters = {"docstatus": 1, "check_out_date": ["is", "not set"]}
    if filters.get("building"):
        query_filters["building"] = filters["building"]
    if filters.get("project"):
        query_filters["project"] = filters["project"]

    rows = frappe.get_all(
        "Accommodation Assignment",
        filters=query_filters,
        fields=[
            "name", "employee", "employee_name", "building", "room", "bed",
            "check_in_date", "project", "cost_center",
        ],
        order_by="building asc, room asc, check_in_date asc",
    )

    return columns, rows
