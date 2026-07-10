# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

import frappe

from apex_habitat.habitat import permissions


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": frappe._("Assignment"), "fieldname": "name", "fieldtype": "Link", "options": "Housing Assignment", "width": 150},
        {"label": frappe._("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": frappe._("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 150},
        {"label": frappe._("Room"), "fieldname": "room", "fieldtype": "Link", "options": "Room", "width": 120},
        {"label": frappe._("Bed"), "fieldname": "bed", "fieldtype": "Link", "options": "Bed", "width": 120},
        {"label": frappe._("Check-in Date"), "fieldname": "check_in_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 140},
        {"label": frappe._("Cost Center"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 140},
    ]

    query_filters = {"docstatus": 1, "check_out_date": ["is", "not set"]}
    if filters.get("building"):
        query_filters["building"] = filters["building"]
    if filters.get("project"):
        query_filters["project"] = filters["project"]

    # get_all forces ignore_permissions, bypassing the building row-scoping the desk
    # list gets via permission_query_conditions — re-apply the caller's building scope
    # (Accommodation Assignment carries a direct building); oversight roles see all.
    user = frappe.session.user
    if not permissions._building_is_unscoped(user):
        allowed = permissions._allowed_buildings(user)
        if not allowed:
            return columns, []
        chosen = query_filters.get("building")
        if chosen and chosen not in allowed:
            return columns, []
        if not chosen:
            query_filters["building"] = ["in", allowed]

    rows = frappe.get_all(
        "Housing Assignment",
        filters=query_filters,
        fields=[
            "name", "employee", "employee_name", "building", "room", "bed",
            "check_in_date", "project", "cost_center",
        ],
        order_by="building asc, room asc, check_in_date asc",
    )

    return columns, rows
