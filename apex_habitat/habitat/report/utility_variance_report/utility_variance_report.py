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
                "label": "Utility Type",
                "fieldname": "utility_type",
                "fieldtype": "Select",
                "width": 120
        },
        {
                "label": "Billing Period",
                "fieldname": "billing_period",
                "fieldtype": "Data",
                "width": 100
        },
        {
                "label": "Amount (SAR)",
                "fieldname": "amount",
                "fieldtype": "Currency",
                "width": 100
        },
        {
                "label": "Consumption",
                "fieldname": "consumption",
                "fieldtype": "Float",
                "width": 100
        },
        {
                "label": "Variance",
                "fieldname": "variance",
                "fieldtype": "Percent",
                "width": 100
        }
]
    data = []
    return columns, data
