# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {
                "label": "Building",
                "fieldname": "building",
                "fieldtype": "Link",
                "options": "Accommodation Building",
                "width": 120
        },
        {
                "label": "Lease Number",
                "fieldname": "lease_number",
                "fieldtype": "Data",
                "width": 120
        },
        {
                "label": "Start Date",
                "fieldname": "start_date",
                "fieldtype": "Date",
                "width": 100
        },
        {
                "label": "End Date",
                "fieldname": "end_date",
                "fieldtype": "Date",
                "width": 100
        },
        {
                "label": "Expiry Status",
                "fieldname": "expiry_status",
                "fieldtype": "Data",
                "width": 100
        }
]
    data = []
    return columns, data
