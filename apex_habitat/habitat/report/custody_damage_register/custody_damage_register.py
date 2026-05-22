# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {
                "label": "Assessment Date",
                "fieldname": "assessment_date",
                "fieldtype": "Date",
                "width": 100
        },
        {
                "label": "Custodian",
                "fieldname": "employee",
                "fieldtype": "Link",
                "options": "Employee",
                "width": 150
        },
        {
                "label": "Asset Category",
                "fieldname": "category",
                "fieldtype": "Link",
                "options": "Custody Asset Category",
                "width": 120
        },
        {
                "label": "Damage Details",
                "fieldname": "details",
                "fieldtype": "Small Text",
                "width": 200
        },
        {
                "label": "Repair Cost (SAR)",
                "fieldname": "repair_cost",
                "fieldtype": "Currency",
                "width": 100
        }
]
    data = []
    return columns, data
