# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {
                "label": frappe._("Request ID"),
                "fieldname": "name",
                "fieldtype": "Link",
                "options": "Maintenance Request",
                "width": 100
        },
        {
                "label": frappe._("Building"),
                "fieldname": "building",
                "fieldtype": "Link",
                "options": "Accommodation Building",
                "width": 120
        },
        {
                "label": frappe._("Description"),
                "fieldname": "description",
                "fieldtype": "Small Text",
                "width": 200
        },
        {
                "label": frappe._("Priority"),
                "fieldname": "priority",
                "fieldtype": "Select",
                "width": 100
        },
        {
                "label": frappe._("Status"),
                "fieldname": "status",
                "fieldtype": "Select",
                "width": 100
        }
]
    data = []
    return columns, data
