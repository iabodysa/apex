# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {
                "label": frappe._("Assessment Date"),
                "fieldname": "assessment_date",
                "fieldtype": "Date",
                "width": 100
        },
        {
                "label": frappe._("Custodian"),
                "fieldname": "employee",
                "fieldtype": "Link",
                "options": "Employee",
                "width": 150
        },
        {
                "label": frappe._("Asset Category"),
                "fieldname": "category",
                "fieldtype": "Link",
                "options": "Custody Asset Category",
                "width": 120
        },
        {
                "label": frappe._("Damage Details"),
                "fieldname": "details",
                "fieldtype": "Small Text",
                "width": 200
        },
        {
                "label": frappe._("Repair Cost (SAR)"),
                "fieldname": "repair_cost",
                "fieldtype": "Currency",
                "width": 100
        }
]
    data = []
    return columns, data
