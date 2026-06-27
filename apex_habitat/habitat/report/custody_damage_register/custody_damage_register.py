# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

import frappe

from apex_habitat.habitat import permissions


def execute(filters=None):
    columns = [
        {"label": frappe._("Assessment"), "fieldname": "name", "fieldtype": "Link", "options": "Custody Damage Assessment", "width": 150},
        {"label": frappe._("Assessment Date"), "fieldname": "assessment_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 150},
        {"label": frappe._("Custodian"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 160},
        {"label": frappe._("Estimated Cost (SAR)"), "fieldname": "total_estimated_replacement_cost_sar", "fieldtype": "Currency", "width": 150},
        {"label": frappe._("Deduction Entry"), "fieldname": "deduction_entry", "fieldtype": "Link", "options": "Additional Salary", "width": 150},
    ]

    query_filters = {"docstatus": 1}
    if filters and filters.get("building"):
        query_filters["building"] = filters["building"]

    # get_all forces ignore_permissions, bypassing the building row-scoping the desk
    # list gets via permission_query_conditions; re-apply the caller's building scope.
    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    if restrict:
        if not allowed:
            return columns, []
        chosen = query_filters.get("building")
        if chosen and chosen not in allowed:
            return columns, []
        if not chosen:
            query_filters["building"] = ["in", allowed]

    data = frappe.get_all(
        "Custody Damage Assessment",
        filters=query_filters,
        fields=[
            "name",
            "assessment_date",
            "building",
            "employee",
            "total_estimated_replacement_cost_sar",
            "deduction_entry",
        ],
        order_by="assessment_date desc",
    )
    return columns, data
