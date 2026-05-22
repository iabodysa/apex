# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {
                "label": "Scheduled Date",
                "fieldname": "execution_date",
                "fieldtype": "Date",
                "width": 100
        },
        {
                "label": "Task",
                "fieldname": "task",
                "fieldtype": "Link",
                "options": "Safety Task Catalog",
                "width": 150
        },
        {
                "label": "Assigned To",
                "fieldname": "executed_by",
                "fieldtype": "Link",
                "options": "User",
                "width": 120
        },
        {
                "label": "Status",
                "fieldname": "execution_status",
                "fieldtype": "Select",
                "width": 100
        }
]
    data = []
    return columns, data
