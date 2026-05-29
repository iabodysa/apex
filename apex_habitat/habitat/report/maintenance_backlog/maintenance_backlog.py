# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {"label": frappe._("Request ID"), "fieldname": "name", "fieldtype": "Link", "options": "Maintenance Request", "width": 140},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 150},
        {"label": frappe._("Issue Type"), "fieldname": "issue_type", "fieldtype": "Data", "width": 120},
        {"label": frappe._("Description"), "fieldname": "description", "fieldtype": "Small Text", "width": 240},
        {"label": frappe._("Priority"), "fieldname": "priority", "fieldtype": "Data", "width": 90},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
    ]

    filters = filters or {}
    query_filters = {"status": ["in", ["Open", "Assigned", "In Progress", "Reopened"]]}
    if filters.get("building"):
        query_filters["building"] = filters["building"]
    if filters.get("company"):
        query_filters["company"] = filters["company"]
    if filters.get("cost_center"):
        query_filters["cost_center"] = filters["cost_center"]

    data = frappe.get_all(
        "Maintenance Request",
        filters=query_filters,
        fields=[
            "name",
            "building",
            "issue_type",
            "issue_description as description",
            "priority",
            "status",
        ],
        order_by="creation asc",
    )
    return columns, data
