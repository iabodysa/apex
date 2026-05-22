# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {"label": frappe._("Execution"), "fieldname": "name", "fieldtype": "Link", "options": "Safety Task Execution", "width": 150},
        {"label": frappe._("Execution Date"), "fieldname": "execution_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 150},
        {"label": frappe._("Task"), "fieldname": "task", "fieldtype": "Link", "options": "Safety Task Catalog", "width": 160},
        {"label": frappe._("Result"), "fieldname": "execution_status", "fieldtype": "Data", "width": 110},
        {"label": frappe._("Executed By"), "fieldname": "executed_by", "fieldtype": "Link", "options": "User", "width": 160},
    ]

    query_filters = {"docstatus": 1}
    if filters and filters.get("building"):
        query_filters["building"] = filters["building"]

    data = frappe.get_all(
        "Safety Task Execution",
        filters=query_filters,
        fields=["name", "execution_date", "building", "task", "execution_status", "executed_by"],
        order_by="execution_date desc",
        limit_page_length=1000,
    )
    return columns, data
