# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

import frappe

from apex_habitat.salis import permissions


def execute(filters=None):
    columns = [
        {"label": frappe._("Claim"), "fieldname": "name", "fieldtype": "Link", "options": "Fuel Claim", "width": 160},
        {"label": frappe._("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 160},
        {"label": frappe._("Period"), "fieldname": "period_month", "fieldtype": "Data", "width": 120},
        {"label": frappe._("Claimed Litres"), "fieldname": "claimed_litres", "fieldtype": "Float", "width": 150},
        {"label": frappe._("Consumed Litres"), "fieldname": "consumed_litres", "fieldtype": "Float", "width": 150},
        {"label": frappe._("Variance Litres"), "fieldname": "variance_litres", "fieldtype": "Float", "width": 150},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 160},
    ]

    query_filters = {}
    if filters:
        if filters.get("status"):
            query_filters["status"] = filters["status"]
        if filters.get("from_date") and filters.get("to_date"):
            query_filters["period_month"] = ["between", [filters["from_date"], filters["to_date"]]]
        elif filters.get("from_date"):
            query_filters["period_month"] = [">=", filters["from_date"]]
        elif filters.get("to_date"):
            query_filters["period_month"] = ["<=", filters["to_date"]]

    # get_all forces ignore_permissions, bypassing the project row-scoping the desk
    # list gets via permission_query_conditions; re-apply the caller's project scope
    # (Fuel Claim carries a direct project); oversight roles see all.
    restrict, allowed = permissions.report_project_scope(frappe.session.user)
    if restrict:
        if not allowed:
            return columns, []
        query_filters["project"] = ["in", allowed]

    data = frappe.get_all(
        "Fuel Claim",
        filters=query_filters,
        fields=[
            "name",
            "vehicle",
            "period_month",
            "claimed_litres",
            "consumed_litres",
            "variance_litres",
            "status",
        ],
        order_by="vehicle asc, period_month asc",
    )

    return columns, data
