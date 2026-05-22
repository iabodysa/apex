# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {
                "label": frappe._("Building"),
                "fieldname": "building",
                "fieldtype": "Link",
                "options": "Accommodation Building",
                "width": 120
        },
        {
                "label": frappe._("Lease Number"),
                "fieldname": "lease_number",
                "fieldtype": "Data",
                "width": 120
        },
        {
                "label": frappe._("Start Date"),
                "fieldname": "start_date",
                "fieldtype": "Date",
                "width": 100
        },
        {
                "label": frappe._("End Date"),
                "fieldname": "end_date",
                "fieldtype": "Date",
                "width": 100
        },
        {
                "label": frappe._("Expiry Status"),
                "fieldname": "expiry_status",
                "fieldtype": "Data",
                "width": 100
        }
]
    data = []
    return columns, data
