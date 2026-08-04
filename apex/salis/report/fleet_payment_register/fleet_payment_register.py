# Copyright (c) 2026, AFMCO and contributors

import frappe

from apex.apex_core.utils.report_helpers import date_range_condition
from apex.salis import permissions


def execute(filters=None):
    columns = [
        {"label": frappe._("Payment"), "fieldname": "name", "fieldtype": "Link", "options": "Salis Payment Request", "width": 180},
        {"label": frappe._("Expense Type"), "fieldname": "expense_type", "fieldtype": "Data", "width": 150},
        {"label": frappe._("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 160},
        {"label": frappe._("Cost Center"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 160},
        {"label": frappe._("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 180},
        {"label": frappe._("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 180},
        {"label": frappe._("Requested By"), "fieldname": "requested_by", "fieldtype": "Data", "width": 160},
        {"label": frappe._("Finance Approved By"), "fieldname": "finance_approved_by", "fieldtype": "Data", "width": 160},
    ]

    query_filters = {}
    if filters:
        for field in ("status", "expense_type", "company", "cost_center", "project"):
            if filters.get(field):
                query_filters[field] = filters[field]
        date_condition = date_range_condition(filters, "creation")
        if date_condition is not None:
            query_filters["creation"] = date_condition

    restrict, allowed = permissions.report_project_scope(frappe.session.user)
    if restrict:
        chosen = query_filters.get("project")
        if not allowed or (chosen and chosen not in allowed):
            return columns, []
        if not chosen:
            query_filters["project"] = ["in", allowed]

    data = frappe.get_all(
        "Salis Payment Request",
        filters=query_filters,
        fields=[
            "name",
            "expense_type",
            "amount",
            "status",
            "company",
            "cost_center",
            "supplier",
            "project",
            "requested_by",
            "finance_approved_by",
            "creation",
        ],
        order_by="creation desc",
    )

    return columns, data
