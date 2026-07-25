# Copyright (c) 2026, AFMCO and contributors
"""Current SIM Custody: every SIM currently held by a custodian, company-scoped."""

import frappe

from apex.logistay import permissions


def execute(filters=None):
    filters = filters or {}
    columns = [
        {"label": frappe._("Mobile Number"), "fieldname": "mobile_number", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": frappe._("Custodian Type"), "fieldname": "current_custodian_type", "fieldtype": "Data", "width": 120},
        {"label": frappe._("Employee"), "fieldname": "current_custodian_employee", "fieldtype": "Link", "options": "Employee", "width": 160},
        {"label": frappe._("Project"), "fieldname": "current_project", "fieldtype": "Link", "options": "Project", "width": 150},
        {"label": frappe._("Cost Center"), "fieldname": "current_cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 160},
        {"label": frappe._("Contract"), "fieldname": "telecom_contract", "fieldtype": "Link", "options": "Telecom Contract", "width": 160},
        {"label": frappe._("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 140},
    ]

    query = {"current_custodian_type": ["!=", "Unassigned"]}
    if filters.get("company"):
        query["company"] = filters["company"]
    if filters.get("status"):
        query["status"] = filters["status"]

    restrict, allowed = permissions.report_company_scope(frappe.session.user)
    if restrict:
        if not allowed:
            return columns, []
        chosen = query.get("company")
        if chosen and chosen not in allowed:
            return columns, []
        if not chosen:
            query["company"] = ["in", allowed]

    data = frappe.get_all(
        "SIM Card",
        filters=query,
        fields=[
            "mobile_number",
            "status",
            "current_custodian_type",
            "current_custodian_employee",
            "current_project",
            "current_cost_center",
            "telecom_contract",
            "supplier",
        ],
        order_by="modified desc",
    )
    return columns, data
