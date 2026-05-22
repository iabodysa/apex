# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 220},
        {"label": frappe._("Active Residents"), "fieldname": "active_residents", "fieldtype": "Int", "width": 150},
    ]

    query_filters = {"docstatus": 1, "check_out_date": ["is", "not set"]}
    if filters and filters.get("building"):
        query_filters["building"] = filters["building"]

    data = frappe.get_all(
        "Accommodation Assignment",
        filters=query_filters,
        fields=["building", "count(name) as active_residents"],
        group_by="building",
        order_by="active_residents desc",
    )
    return columns, data
