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
                "label": frappe._("Utility Type"),
                "fieldname": "utility_type",
                "fieldtype": "Select",
                "width": 120
        },
        {
                "label": frappe._("Billing Period"),
                "fieldname": "billing_period",
                "fieldtype": "Data",
                "width": 100
        },
        {
                "label": frappe._("Amount (SAR)"),
                "fieldname": "amount",
                "fieldtype": "Currency",
                "width": 100
        },
        {
                "label": frappe._("Consumption"),
                "fieldname": "consumption",
                "fieldtype": "Float",
                "width": 100
        },
        {
                "label": frappe._("Variance"),
                "fieldname": "variance",
                "fieldtype": "Percent",
                "width": 100
        }
]
    data = []
    return columns, data
